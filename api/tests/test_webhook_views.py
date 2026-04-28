"""Тесты webhook endpoint-а Stripe.

В этом наборе проверяем два ключевых свойства интеграции:
1. endpoint не принимает неподписанные или поддельные события;
2. валидный Stripe event действительно обновляет локальный заказ в БД.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from api.models import Item, Order, OrderItem, PaymentStatus
from api.services.webhooks import InvalidStripeWebhookSignatureError


@override_settings(STRIPE_WEBHOOK_SECRET='whsec_test_secret')
class StripeWebhookViewTests(TestCase):
    """Проверки приема и обработки Stripe webhook-событий."""

    def setUp(self):
        """Создает заказ, который webhook затем будет переводить по статусам."""
        self.item = Item.objects.create(
            name='Webhook item',
            description='Webhook item description',
            price=Decimal('19.99'),
            currency='usd',
        )
        self.order = Order.objects.create(
            currency='usd',
            payment_status=PaymentStatus.PENDING,
            stripe_session_id='cs_test_pending',
        )
        OrderItem.objects.create(order=self.order, item=self.item, quantity=1)

    @patch('api.views.webhook.construct_stripe_event_from_webhook')
    def test_webhook_marks_order_as_paid_on_checkout_completed(self, mocked_construct_event):
        """Событие `checkout.session.completed` должно переводить заказ в `paid`."""
        mocked_construct_event.return_value = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_pending',
                    'payment_status': 'paid',
                    'payment_intent': 'pi_test_paid',
                    'status': 'complete',
                    'metadata': {
                        'order_id': str(self.order.pk),
                    },
                }
            },
        }

        response = self.client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=test_signature',
        )

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)
        self.assertEqual(self.order.stripe_payment_intent_id, 'pi_test_paid')
        self.assertIsNotNone(self.order.paid_at)

    @patch('api.views.webhook.construct_stripe_event_from_webhook')
    def test_webhook_marks_order_as_failed_on_payment_intent_failure(self, mocked_construct_event):
        """Событие `payment_intent.payment_failed` должно фиксировать неуспех оплаты."""
        mocked_construct_event.return_value = {
            'type': 'payment_intent.payment_failed',
            'data': {
                'object': {
                    'id': 'pi_test_failed',
                    'metadata': {
                        'order_id': str(self.order.pk),
                    },
                }
            },
        }

        response = self.client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=test_signature',
        )

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.FAILED)
        self.assertEqual(self.order.stripe_payment_intent_id, 'pi_test_failed')

    @patch('api.views.webhook.construct_stripe_event_from_webhook')
    def test_webhook_returns_400_for_invalid_signature(self, mocked_construct_event):
        """Поддельная подпись Stripe должна отклоняться без изменения БД."""
        mocked_construct_event.side_effect = InvalidStripeWebhookSignatureError(
            'Некорректная подпись Stripe webhook.'
        )

        response = self.client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=broken_signature',
        )

        self.assertEqual(response.status_code, 400)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    @patch('api.views.webhook.construct_stripe_event_from_webhook')
    def test_webhook_ignores_replayed_event(self, mocked_construct_event):
        """Повторная доставка того же `event.id` не должна снова мутировать заказ.

        Stripe гарантирует at-least-once доставку, поэтому без журнала
        `ProcessedStripeEvent` второй приход того же события мог бы повторно
        сдвинуть `paid_at` или сменить статус.
        """
        mocked_construct_event.return_value = {
            'id': 'evt_test_replay',
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_pending',
                    'payment_status': 'paid',
                    'payment_intent': 'pi_test_paid',
                    'status': 'complete',
                    'metadata': {'order_id': str(self.order.pk)},
                }
            },
        }

        first_response = self.client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=test_signature',
        )
        self.assertEqual(first_response.status_code, 200)

        self.order.refresh_from_db()
        first_paid_at = self.order.paid_at
        self.assertIsNotNone(first_paid_at)

        # Эмулируем "поломку" заказа в БД, чтобы повторная обработка была заметна.
        self.order.payment_status = PaymentStatus.PROCESSING
        self.order.save(update_fields=('payment_status',))

        second_response = self.client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=test_signature',
        )
        self.assertEqual(second_response.status_code, 200)

        self.order.refresh_from_db()
        # Replay не должен вернуть статус в PAID — обработка повторно не запустилась.
        self.assertEqual(self.order.payment_status, PaymentStatus.PROCESSING)

    @patch('api.views.webhook.construct_stripe_event_from_webhook')
    def test_webhook_passes_csrf_check(self, mocked_construct_event):
        """Webhook должен принимать POST даже при включенной CSRF-проверке.

        Stripe не передает CSRF-токен и cookies, поэтому без `@csrf_exempt`
        `CsrfViewMiddleware` отклонит запрос с 403 еще до проверки подписи.
        """
        mocked_construct_event.return_value = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_pending',
                    'payment_status': 'paid',
                    'payment_intent': 'pi_test_paid',
                    'status': 'complete',
                    'metadata': {'order_id': str(self.order.pk)},
                }
            },
        }

        csrf_strict_client = Client(enforce_csrf_checks=True)
        response = csrf_strict_client.post(
            reverse('api:stripe-webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=123,v1=test_signature',
        )

        self.assertEqual(response.status_code, 200)
