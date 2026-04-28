"""Тесты HTTP-endpoint-ов запуска Checkout Session flow."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import stripe
from django.test import TestCase
from django.urls import reverse

from api.models import CheckoutMode, Item, Order, OrderItem, PaymentStatus


class BuyItemViewTests(TestCase):
    """Проверки JSON-endpoint `/buy/<id>`."""

    def setUp(self):
        """Создает тестовый товар для запуска Stripe Checkout."""
        self.item = Item.objects.create(
            name='Checkout item',
            description='Checkout item description',
            price=Decimal('49.99'),
            currency='usd',
        )

    @patch(
        'api.views.checkout.start_checkout_session_for_item_purchase',
        new_callable=AsyncMock,
    )
    def test_buy_item_returns_session_id(self, mocked_start_checkout):
        """Успешный запрос должен вернуть `session.id` из service-слоя."""
        mocked_start_checkout.return_value = SimpleNamespace(id='cs_test_123')

        response = self.client.get(reverse('api:buy-item', args=[self.item.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': 'cs_test_123'})
        mocked_start_checkout.assert_awaited_once_with(self.item)

    @patch(
        'api.views.checkout.start_checkout_session_for_item_purchase',
        new_callable=AsyncMock,
    )
    def test_buy_item_returns_502_when_stripe_fails(self, mocked_start_checkout):
        """Ошибка Stripe должна возвращаться как контролируемый JSON-ответ."""
        mocked_start_checkout.side_effect = stripe.StripeError('Stripe is unavailable')

        response = self.client.get(reverse('api:buy-item', args=[self.item.pk]))

        self.assertEqual(response.status_code, 502)
        self.assertIn('error', response.json())

    def test_buy_item_returns_404_for_unknown_item(self):
        """Несуществующий товар не должен приводить к 500 в checkout view."""
        response = self.client.get(reverse('api:buy-item', args=[999999]))

        self.assertEqual(response.status_code, 404)


class BuyOrderViewTests(TestCase):
    """Проверки JSON-endpoint `/buy-order/<id>`."""

    def setUp(self):
        """Создает заказ с несколькими позициями для Stripe Checkout."""
        self.first_item = Item.objects.create(
            name='First order item',
            description='First order item description',
            price=Decimal('10.00'),
            currency='usd',
        )
        self.second_item = Item.objects.create(
            name='Second order item',
            description='Second order item description',
            price=Decimal('15.50'),
            currency='usd',
        )
        self.order = Order.objects.create(currency='usd')
        OrderItem.objects.create(order=self.order, item=self.first_item, quantity=2)
        OrderItem.objects.create(order=self.order, item=self.second_item, quantity=1)

    @patch(
        'api.views.checkout.start_checkout_session_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_returns_session_id(self, mocked_start_checkout):
        """Успешный checkout по заказу должен вернуть `session.id`."""
        mocked_start_checkout.return_value = SimpleNamespace(id='cs_test_order_123')

        response = self.client.get(reverse('api:buy-order', args=[self.order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': 'cs_test_order_123'})
        mocked_start_checkout.assert_awaited_once()

    @patch(
        'api.views.checkout.start_checkout_session_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_returns_400_for_invalid_order_payload(self, mocked_start_checkout):
        """Ошибки подготовки payload должны возвращаться как 400."""
        mocked_start_checkout.side_effect = ValueError('Пустой заказ.')

        response = self.client.get(reverse('api:buy-order', args=[self.order.pk]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'Пустой заказ.'})

    @patch(
        'api.views.checkout.start_checkout_session_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_returns_502_when_stripe_fails(self, mocked_start_checkout):
        """Ошибки Stripe в order-flow должны обрабатываться так же, как в item-flow."""
        mocked_start_checkout.side_effect = stripe.StripeError('Stripe order failure')

        response = self.client.get(reverse('api:buy-order', args=[self.order.pk]))

        self.assertEqual(response.status_code, 502)
        self.assertIn('error', response.json())

    def test_buy_order_returns_404_for_unknown_order(self):
        """Несуществующий заказ должен отдавать 404."""
        response = self.client.get(reverse('api:buy-order', args=[999999]))

        self.assertEqual(response.status_code, 404)


class BuyOrderPaymentIntentViewTests(TestCase):
    """Проверки JSON-endpoint `/buy-order-payment-intent/<id>`."""

    def setUp(self):
        """Создает заказ для отдельного Payment Intent flow."""
        self.item = Item.objects.create(
            name='Payment intent order item',
            description='Payment intent order item description',
            price=Decimal('20.00'),
            currency='usd',
        )
        self.order = Order.objects.create(currency='usd')
        OrderItem.objects.create(order=self.order, item=self.item, quantity=2)

    @patch(
        'api.views.checkout.start_payment_intent_checkout_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_payment_intent_returns_client_secret_payload(self, mocked_start_payment_intent):
        """Endpoint должен возвращать `client_secret` и `payment_intent_id`."""
        mocked_start_payment_intent.return_value = {
            'payment_intent_id': 'pi_test_123',
            'client_secret': 'pi_test_123_secret',
            'return_url': 'http://localhost:8000/success?order_id=1',
        }

        response = self.client.get(
            reverse('api:buy-order-payment-intent', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'payment_intent_id': 'pi_test_123',
                'client_secret': 'pi_test_123_secret',
                'return_url': 'http://localhost:8000/success?order_id=1',
            },
        )

    @patch(
        'api.views.checkout.start_payment_intent_checkout_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_payment_intent_returns_400_for_invalid_order_payload(self, mocked_start_payment_intent):
        """Ошибки подготовки PaymentIntent должны возвращаться как 400."""
        mocked_start_payment_intent.side_effect = ValueError('Пустой заказ.')

        response = self.client.get(
            reverse('api:buy-order-payment-intent', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'Пустой заказ.'})

    @patch(
        'api.views.checkout.start_payment_intent_checkout_for_order',
        new_callable=AsyncMock,
    )
    def test_buy_order_payment_intent_returns_502_when_stripe_fails(self, mocked_start_payment_intent):
        """Stripe-ошибка в Payment Intent flow должна конвертироваться в 502."""
        mocked_start_payment_intent.side_effect = stripe.StripeError('PaymentIntent failure')

        response = self.client.get(
            reverse('api:buy-order-payment-intent', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn('error', response.json())

    def test_buy_order_payment_intent_returns_404_for_unknown_order(self):
        """Несуществующий заказ на Payment Intent endpoint должен отдавать 404."""
        response = self.client.get(
            reverse('api:buy-order-payment-intent', args=[999999])
        )

        self.assertEqual(response.status_code, 404)


class CheckoutResultPageTests(TestCase):
    """Проверки success/cancel страниц после возврата из Stripe Checkout."""

    @patch(
        'api.views.checkout.sync_order_after_stripe_return',
        new_callable=AsyncMock,
    )
    def test_success_page_attempts_to_sync_order_by_session_id(self, mocked_sync):
        """Success-страница должна пытаться синхронизировать заказ по session_id."""
        response = self.client.get(
            reverse('api:checkout-success'),
            {'session_id': 'cs_test_sync', 'order_id': '17'},
        )

        self.assertEqual(response.status_code, 200)
        mocked_sync.assert_awaited_once_with(
            session_id='cs_test_sync',
            payment_intent_id='',
            order_id='17',
        )

    @patch(
        'api.views.checkout.sync_order_after_stripe_return',
        new_callable=AsyncMock,
    )
    def test_success_page_attempts_to_sync_order_by_payment_intent_id(self, mocked_sync):
        """Success-страница должна уметь синхронизировать Payment Intent flow."""
        response = self.client.get(
            reverse('api:checkout-success'),
            {
                'payment_intent_id': 'pi_test_sync',
                'order_id': '22',
                'payment_flow': 'payment_intent',
            },
        )

        self.assertEqual(response.status_code, 200)
        mocked_sync.assert_awaited_once_with(
            session_id='',
            payment_intent_id='pi_test_sync',
            order_id='22',
        )
