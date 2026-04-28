"""Тесты сервисного слоя Stripe webhook и post-return синхронизации.

Здесь проверяем уже не HTTP-обвязку, а именно сервисные контракты:
1. корректно ли service-слой валидирует и нормализует webhook-событие;
2. правильно ли сервис подбирает валюту заказа при синхронизации после
   возврата пользователя со Stripe.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import stripe
from asgiref.sync import async_to_sync
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Order
from api.services.webhooks import (
    InvalidStripeWebhookPayloadError,
    InvalidStripeWebhookSignatureError,
    construct_stripe_event_from_webhook,
    sync_order_from_checkout_session_object,
    sync_order_from_payment_intent_object,
    sync_order_after_stripe_return,
)


class ConstructStripeEventFromWebhookTests(TestCase):
    """Проверки верификации Stripe webhook внутри service-слоя."""

    @patch('api.services.webhooks.stripe.Webhook.construct_event')
    def test_construct_stripe_event_from_webhook_returns_verified_event(self, mocked_construct_event):
        """При корректных данных сервис должен вернуть Stripe event как есть."""
        mocked_construct_event.return_value = {'type': 'checkout.session.completed'}

        event = construct_stripe_event_from_webhook(
            payload=b'{}',
            signature='t=123,v1=test_signature',
            webhook_secret='whsec_test_secret',
        )

        self.assertEqual(event, {'type': 'checkout.session.completed'})
        mocked_construct_event.assert_called_once()

    def test_construct_stripe_event_from_webhook_requires_secret(self):
        """Без webhook secret сервис не должен пытаться доверять входящему событию."""
        with self.assertRaises(ImproperlyConfigured):
            construct_stripe_event_from_webhook(
                payload=b'{}',
                signature='t=123,v1=test_signature',
                webhook_secret='',
            )

    @patch('api.services.webhooks.stripe.Webhook.construct_event')
    def test_construct_stripe_event_from_webhook_wraps_payload_error(self, mocked_construct_event):
        """Некорректный payload должен превращаться в сервисную ошибку."""
        mocked_construct_event.side_effect = ValueError('Broken payload')

        with self.assertRaises(InvalidStripeWebhookPayloadError):
            construct_stripe_event_from_webhook(
                payload=b'broken',
                signature='t=123,v1=test_signature',
                webhook_secret='whsec_test_secret',
            )

    @patch('api.services.webhooks.stripe.Webhook.construct_event')
    def test_construct_stripe_event_from_webhook_wraps_signature_error(self, mocked_construct_event):
        """Некорректная подпись должна давать доменную ошибку service-слоя."""
        mocked_construct_event.side_effect = stripe.SignatureVerificationError(
            message='Invalid signature',
            sig_header='broken_signature',
        )

        with self.assertRaises(InvalidStripeWebhookSignatureError):
            construct_stripe_event_from_webhook(
                payload=b'{}',
                signature='t=123,v1=broken_signature',
                webhook_secret='whsec_test_secret',
            )


@override_settings(STRIPE_WEBHOOK_SECRET='whsec_test_secret')
class SyncOrderAfterStripeReturnTests(TestCase):
    """Проверки best-effort синхронизации после возврата пользователя со Stripe."""

    def setUp(self):
        """Создает заказ, чья валюта должна использоваться для Stripe client routing."""
        self.order = Order.objects.create(currency='eur')

    @patch('api.services.webhooks.sync_order_from_payment_intent_id', new_callable=AsyncMock)
    @patch('api.services.webhooks.sync_order_from_checkout_session_id', new_callable=AsyncMock)
    def test_sync_order_after_stripe_return_uses_order_currency(self, mocked_sync_checkout, mocked_sync_payment_intent):
        """Если order_id известен, сервис должен пробросить валюту заказа в оба sync-вызова."""
        async_to_sync(sync_order_after_stripe_return)(
            session_id='cs_test_sync',
            payment_intent_id='pi_test_sync',
            order_id=str(self.order.pk),
        )

        mocked_sync_checkout.assert_awaited_once_with(
            'cs_test_sync',
            currency='eur',
        )
        mocked_sync_payment_intent.assert_awaited_once_with(
            'pi_test_sync',
            currency='eur',
        )

    @patch('api.services.webhooks.sync_order_from_checkout_session_id', new_callable=AsyncMock)
    def test_sync_order_after_stripe_return_falls_back_to_unknown_currency(self, mocked_sync_checkout):
        """Если заказ не найден, сервис все равно должен попытаться синхронизировать статус."""
        async_to_sync(sync_order_after_stripe_return)(
            session_id='cs_test_sync',
            order_id='999999',
        )

        mocked_sync_checkout.assert_awaited_once_with(
            'cs_test_sync',
            currency=None,
        )


class WebhookPaidAtStabilityTests(TestCase):
    """Проверки того, что повторные Stripe-события не затирают первую дату оплаты."""

    def test_checkout_session_sync_keeps_existing_paid_at_timestamp(self):
        """Повторный paid webhook не должен менять уже записанное `paid_at`.

        Stripe ретраит webhook-события штатно, поэтому первая успешная дата
        оплаты должна считаться источником истины и оставаться неизменной.
        """
        initial_paid_at = timezone.now() - timedelta(hours=3)
        order = Order.objects.create(
            currency='usd',
            payment_status='pending',
            stripe_session_id='cs_paid_123',
            paid_at=initial_paid_at,
        )

        async_to_sync(sync_order_from_checkout_session_object)(
            {
                'id': 'cs_paid_123',
                'payment_status': 'paid',
                'status': 'complete',
                'payment_intent': 'pi_paid_123',
                'metadata': {
                    'order_id': str(order.pk),
                },
            }
        )

        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.paid_at, initial_paid_at)

    def test_payment_intent_sync_keeps_existing_paid_at_timestamp(self):
        """Повторный `payment_intent.succeeded` не должен затирать `paid_at`."""
        initial_paid_at = timezone.now() - timedelta(hours=1)
        order = Order.objects.create(
            currency='usd',
            payment_status='pending',
            stripe_payment_intent_id='pi_paid_123',
            paid_at=initial_paid_at,
        )

        async_to_sync(sync_order_from_payment_intent_object)(
            {
                'id': 'pi_paid_123',
                'status': 'succeeded',
                'metadata': {
                    'order_id': str(order.pk),
                },
            }
        )

        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.paid_at, initial_paid_at)
