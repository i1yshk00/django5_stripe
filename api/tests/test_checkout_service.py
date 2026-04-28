"""Тесты сервисного слоя Stripe Checkout."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings

from api.models import Discount, DiscountType, Item, Order, OrderItem, Tax
from api.services.checkout import (
    build_item_checkout_session_params,
    build_order_checkout_session_params,
    build_order_payment_intent_params,
    create_order_for_item_purchase,
    create_checkout_session_for_item,
    create_checkout_session_for_order,
    create_payment_intent_for_order,
    get_or_create_payment_intent_for_order,
    start_checkout_session_for_item_purchase,
    start_checkout_session_for_order,
    start_payment_intent_checkout_for_order,
)


@override_settings(
    DOMAIN_URL='http://localhost:8000',
    STRIPE_SECRET_KEY='sk_test_service',
    STRIPE_PUBLISHABLE_KEY='pk_test_service',
    STRIPE_API_VERSION='2026-02-25.clover',
)
class CheckoutServiceTests(TestCase):
    """Проверки payload и вызова Stripe SDK на сервисном слое."""

    def setUp(self):
        """Создает товар и заказ, на основе которых строится Stripe payload."""
        self.item = Item.objects.create(
            name='Service item',
            description='Service description',
            price=Decimal('12.34'),
            currency='usd',
        )
        self.order = Order.objects.create(currency='usd')
        self.order_item = OrderItem.objects.create(
            order=self.order,
            item=self.item,
            quantity=3,
        )

    def test_build_item_checkout_session_params(self):
        """Payload должен содержать обязательные поля Checkout Session."""
        payload = build_item_checkout_session_params(self.item)

        self.assertEqual(payload['mode'], 'payment')
        self.assertEqual(
            payload['success_url'],
            f'http://localhost:8000/success?session_id={{CHECKOUT_SESSION_ID}}&item_id={self.item.pk}',
        )
        self.assertEqual(
            payload['cancel_url'],
            f'http://localhost:8000/cancel?item_id={self.item.pk}',
        )
        self.assertEqual(payload['metadata']['item_id'], str(self.item.pk))
        self.assertEqual(payload['line_items'][0]['quantity'], 1)
        self.assertEqual(payload['line_items'][0]['price_data']['currency'], 'usd')
        self.assertEqual(payload['line_items'][0]['price_data']['unit_amount'], 1234)
        self.assertEqual(
            payload['line_items'][0]['price_data']['product_data']['name'],
            'Service item',
        )

    def test_build_item_checkout_session_params_includes_order_metadata(self):
        """Если под item flow уже создан заказ, его нужно пробросить в metadata."""
        payload = build_item_checkout_session_params(self.item, order=self.order)

        self.assertEqual(payload['client_reference_id'], str(self.order.pk))
        self.assertEqual(payload['metadata']['order_id'], str(self.order.pk))
        self.assertEqual(
            payload['success_url'],
            (
                'http://localhost:8000/success'
                f'?session_id={{CHECKOUT_SESSION_ID}}&item_id={self.item.pk}&order_id={self.order.pk}'
            ),
        )

    def test_create_order_for_item_purchase_creates_local_sale_record(self):
        """Прямая покупка товара должна сразу получать локальный заказ в БД."""
        created_order = async_to_sync(create_order_for_item_purchase)(self.item)

        created_order.refresh_from_db()
        created_order_item = OrderItem.objects.get(order=created_order)

        self.assertEqual(created_order.currency, 'usd')
        self.assertEqual(created_order.payment_status, 'draft')
        self.assertEqual(created_order.checkout_mode, 'checkout_session')
        self.assertEqual(created_order_item.item_id, self.item.pk)
        self.assertEqual(created_order_item.quantity, 1)

    @patch('api.services.checkout.create_checkout_session_for_item', new_callable=AsyncMock)
    def test_start_checkout_session_for_item_purchase_updates_order_state(self, mocked_create_session):
        """Верхнеуровневый item-checkout должен сам создать и обновить заказ."""
        mocked_create_session.return_value = SimpleNamespace(id='cs_started_item_123')

        session = async_to_sync(start_checkout_session_for_item_purchase)(self.item)

        self.assertEqual(session.id, 'cs_started_item_123')
        order = Order.objects.filter(order_items__item=self.item).latest('id')

        self.assertEqual(order.checkout_mode, 'checkout_session')
        self.assertEqual(order.payment_status, 'pending')
        self.assertEqual(order.stripe_session_id, 'cs_started_item_123')

    @patch('api.services.checkout.create_checkout_session_for_item', new_callable=AsyncMock)
    def test_start_checkout_session_for_item_purchase_marks_order_failed_when_stripe_creation_crashes(self, mocked_create_session):
        """При сбое Stripe локальный заказ не должен оставаться в состоянии draft.

        Для item-flow это особенно важно: заказ создается заранее, еще до вызова
        Stripe API. Если запрос в Stripe падает, запись о попытке покупки должна
        сохраниться как `failed`, а не как незавершенный черновик.
        """
        mocked_create_session.side_effect = RuntimeError('Stripe is unavailable')

        with self.assertRaises(RuntimeError):
            async_to_sync(start_checkout_session_for_item_purchase)(self.item)

        order = Order.objects.filter(order_items__item=self.item).latest('id')
        self.assertEqual(order.checkout_mode, 'checkout_session')
        self.assertEqual(order.payment_status, 'failed')
        self.assertEqual(order.stripe_session_id, '')

    @patch('api.services.checkout.get_stripe_client_for_currency')
    def test_create_checkout_session_for_item_uses_async_stripe_client(self, mocked_get_client):
        """Сервис должен вызывать async-метод Stripe SDK с правильным payload."""
        create_async = AsyncMock(return_value=SimpleNamespace(id='cs_test_service'))
        mocked_get_client.return_value = SimpleNamespace(
            v1=SimpleNamespace(
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(create_async=create_async),
                )
            )
        )

        session = async_to_sync(create_checkout_session_for_item)(self.item)

        self.assertEqual(session.id, 'cs_test_service')
        mocked_get_client.assert_called_once_with('usd')
        self.assertEqual(
            create_async.await_args.kwargs['params']['line_items'][0]['price_data']['unit_amount'],
            1234,
        )

    def test_build_order_checkout_session_params(self):
        """Payload заказа должен содержать несколько line items и метаданные заказа."""
        payload = build_order_checkout_session_params(
            Order.objects.prefetch_related('order_items').get(pk=self.order.pk)
        )

        self.assertEqual(payload['mode'], 'payment')
        self.assertEqual(payload['client_reference_id'], str(self.order.pk))
        self.assertEqual(
            payload['success_url'],
            f'http://localhost:8000/success?session_id={{CHECKOUT_SESSION_ID}}&order_id={self.order.pk}',
        )
        self.assertEqual(
            payload['cancel_url'],
            f'http://localhost:8000/cancel?order_id={self.order.pk}',
        )
        self.assertEqual(payload['metadata']['order_id'], str(self.order.pk))
        self.assertEqual(payload['line_items'][0]['quantity'], 3)
        self.assertEqual(payload['line_items'][0]['price_data']['currency'], 'usd')
        self.assertEqual(payload['line_items'][0]['price_data']['unit_amount'], 1234)
        self.assertEqual(
            payload['line_items'][0]['price_data']['product_data']['name'],
            'Service item',
        )

    def test_build_order_checkout_session_params_includes_discount_and_tax(self):
        """Если в заказе уже есть скидка и налог, они должны уйти в Stripe payload."""
        discount = Discount.objects.create(
            name='Ten percent off',
            stripe_coupon_id='coupon_10_off',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        tax = Tax.objects.create(
            name='VAT 20%',
            stripe_tax_rate_id='txr_20',
            percentage=Decimal('20.00'),
            inclusive=False,
        )
        self.order.discount = discount
        self.order.tax = tax
        self.order.save()

        payload = build_order_checkout_session_params(
            Order.objects.select_related('discount', 'tax').prefetch_related('order_items').get(pk=self.order.pk)
        )

        self.assertEqual(payload['discounts'], [{'coupon': 'coupon_10_off'}])
        self.assertEqual(payload['line_items'][0]['tax_rates'], ['txr_20'])

    def test_build_order_checkout_session_params_rejects_empty_order(self):
        """Пустой заказ нельзя отправлять в Stripe Checkout."""
        empty_order = Order.objects.create(currency='usd')

        with self.assertRaisesMessage(
            ValueError,
            'Нельзя создать Checkout Session для пустого заказа.',
        ):
            build_order_checkout_session_params(
                Order.objects.prefetch_related('order_items').get(pk=empty_order.pk)
            )

    def test_build_order_payment_intent_params(self):
        """PaymentIntent payload должен собираться из итоговой суммы заказа."""
        payload = build_order_payment_intent_params(
            Order.objects.select_related('discount', 'tax').prefetch_related('order_items').get(pk=self.order.pk)
        )

        self.assertEqual(payload['amount'], 3702)
        self.assertEqual(payload['currency'], 'usd')
        self.assertEqual(payload['metadata']['order_id'], str(self.order.pk))
        self.assertEqual(payload['metadata']['payment_flow'], 'payment_intent')
        self.assertEqual(payload['automatic_payment_methods'], {'enabled': True})

    def test_build_order_payment_intent_params_rejects_empty_order(self):
        """Пустой заказ нельзя превращать в PaymentIntent."""
        empty_order = Order.objects.create(currency='usd')

        with self.assertRaisesMessage(
            ValueError,
            'Нельзя создать PaymentIntent для пустого заказа.',
        ):
            build_order_payment_intent_params(
                Order.objects.prefetch_related('order_items').get(pk=empty_order.pk)
            )

    @patch('api.services.checkout.get_stripe_client_for_currency')
    def test_create_checkout_session_for_order_uses_async_stripe_client(self, mocked_get_client):
        """Сервис заказа должен вызывать async Stripe client так же, как item-flow."""
        create_async = AsyncMock(return_value=SimpleNamespace(id='cs_test_order'))
        mocked_get_client.return_value = SimpleNamespace(
            v1=SimpleNamespace(
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(create_async=create_async),
                )
            )
        )

        order = Order.objects.prefetch_related('order_items').get(pk=self.order.pk)
        session = async_to_sync(create_checkout_session_for_order)(order)

        self.assertEqual(session.id, 'cs_test_order')
        mocked_get_client.assert_called_once_with('usd')
        self.assertEqual(
            create_async.await_args.kwargs['params']['metadata']['order_id'],
            str(self.order.pk),
        )

    @patch('api.services.checkout.create_checkout_session_for_order', new_callable=AsyncMock)
    def test_start_checkout_session_for_order_updates_order_state(self, mocked_create_session):
        """Верхнеуровневый order-checkout должен сам сохранять pending-статус."""
        mocked_create_session.return_value = SimpleNamespace(id='cs_started_order_123')

        order = Order.objects.prefetch_related('order_items').get(pk=self.order.pk)
        session = async_to_sync(start_checkout_session_for_order)(order)

        self.assertEqual(session.id, 'cs_started_order_123')
        self.order.refresh_from_db()
        self.assertEqual(self.order.checkout_mode, 'checkout_session')
        self.assertEqual(self.order.payment_status, 'pending')
        self.assertEqual(self.order.stripe_session_id, 'cs_started_order_123')

    @patch('api.services.checkout.create_checkout_session_for_order', new_callable=AsyncMock)
    def test_start_checkout_session_for_order_marks_order_failed_when_stripe_creation_crashes(self, mocked_create_session):
        """Ошибка при создании Checkout Session должна оставлять явный `failed`."""
        mocked_create_session.side_effect = RuntimeError('Stripe is unavailable')

        order = Order.objects.prefetch_related('order_items').get(pk=self.order.pk)

        with self.assertRaises(RuntimeError):
            async_to_sync(start_checkout_session_for_order)(order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.checkout_mode, 'checkout_session')
        self.assertEqual(self.order.payment_status, 'failed')
        self.assertEqual(self.order.stripe_session_id, '')

    @patch('api.services.checkout.get_stripe_client_for_currency')
    def test_create_payment_intent_for_order_uses_async_stripe_client(self, mocked_get_client):
        """PaymentIntent flow должен использовать async Stripe client по валюте заказа."""
        create_async = AsyncMock(
            return_value=SimpleNamespace(
                id='pi_test_order',
                client_secret='pi_test_order_secret',
            )
        )
        mocked_get_client.return_value = SimpleNamespace(
            v1=SimpleNamespace(
                payment_intents=SimpleNamespace(create_async=create_async),
            )
        )

        order = Order.objects.prefetch_related('order_items').get(pk=self.order.pk)
        payment_intent = async_to_sync(create_payment_intent_for_order)(order)

        self.assertEqual(payment_intent.id, 'pi_test_order')
        mocked_get_client.assert_called_once_with('usd')
        self.assertEqual(
            create_async.await_args.kwargs['params']['metadata']['order_id'],
            str(self.order.pk),
        )

    @patch('api.services.checkout.create_payment_intent_for_order', new_callable=AsyncMock)
    def test_get_or_create_payment_intent_for_order_saves_payment_intent_state(self, mocked_create_payment_intent):
        """При первом вызове сервис должен создать PaymentIntent и сохранить его в заказе."""
        mocked_create_payment_intent.return_value = SimpleNamespace(
            id='pi_created_123',
            client_secret='pi_created_123_secret',
        )

        payload = async_to_sync(get_or_create_payment_intent_for_order)(self.order)

        self.order.refresh_from_db()
        self.assertEqual(payload['payment_intent_id'], 'pi_created_123')
        self.assertEqual(payload['client_secret'], 'pi_created_123_secret')
        self.assertIn(f'order_id={self.order.pk}', payload['return_url'])
        self.assertEqual(self.order.checkout_mode, 'payment_intent')
        self.assertEqual(self.order.payment_status, 'pending')
        self.assertEqual(self.order.stripe_payment_intent_id, 'pi_created_123')
        self.assertEqual(self.order.stripe_client_secret, 'pi_created_123_secret')

    def test_get_or_create_payment_intent_for_order_reuses_existing_intent(self):
        """Повторный вызов не должен плодить новые PaymentIntent без необходимости."""
        self.order.checkout_mode = 'payment_intent'
        self.order.payment_status = 'pending'
        self.order.stripe_payment_intent_id = 'pi_existing_123'
        self.order.stripe_client_secret = 'pi_existing_123_secret'
        self.order.save()

        payload = async_to_sync(get_or_create_payment_intent_for_order)(self.order)

        self.assertEqual(payload['payment_intent_id'], 'pi_existing_123')
        self.assertEqual(payload['client_secret'], 'pi_existing_123_secret')

    @patch('api.services.checkout.create_payment_intent_for_order', new_callable=AsyncMock)
    def test_get_or_create_payment_intent_for_order_marks_order_failed_when_creation_crashes(self, mocked_create_payment_intent):
        """Если Stripe не смог создать PaymentIntent, заказ должен стать failed."""
        mocked_create_payment_intent.side_effect = RuntimeError('Stripe is unavailable')

        with self.assertRaises(RuntimeError):
            async_to_sync(get_or_create_payment_intent_for_order)(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.checkout_mode, 'payment_intent')
        self.assertEqual(self.order.payment_status, 'failed')
        self.assertEqual(self.order.stripe_payment_intent_id, '')
        self.assertEqual(self.order.stripe_client_secret, '')

    @patch('api.services.checkout.get_or_create_payment_intent_for_order', new_callable=AsyncMock)
    def test_start_payment_intent_checkout_for_order_uses_service_entrypoint(self, mocked_get_or_create):
        """View должен иметь отдельную верхнеуровневую точку входа для Payment Intent."""
        mocked_get_or_create.return_value = {
            'payment_intent_id': 'pi_started_123',
            'client_secret': 'pi_started_123_secret',
            'return_url': 'http://localhost:8000/success?order_id=1',
        }

        payload = async_to_sync(start_payment_intent_checkout_for_order)(self.order)

        self.assertEqual(
            payload,
            {
                'payment_intent_id': 'pi_started_123',
                'client_secret': 'pi_started_123_secret',
                'return_url': 'http://localhost:8000/success?order_id=1',
            },
        )
