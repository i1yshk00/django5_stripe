"""Тесты выбора Stripe keypair по валюте.

Этот набор проверяет именно 7 этап `steps.md`:
- сервисный слой должен уметь выбирать разные ключи по валюте;
- при отсутствии отдельных валютных ключей приложение должно корректно
  использовать общий keypair одного Stripe account.
"""

from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from api.services.stripe_client import (
    _clear_stripe_client_cache,
    get_publishable_key_for_currency,
    get_stripe_client_for_currency,
    get_sync_stripe_client_for_currency,
)


class StripeClientRoutingTests(SimpleTestCase):
    """Проверки currency-routing для publishable и secret key."""

    def setUp(self):
        """Гарантирует чистый старт каждого теста — настройки только что override."""
        _clear_stripe_client_cache()

    def tearDown(self):
        """Очищает cache фабрик клиентов между тестами."""
        _clear_stripe_client_cache()

    @override_settings(
        STRIPE_API_VERSION='2026-02-25.clover',
        STRIPE_CURRENCY_KEYPAIRS={
            'usd': {
                'secret_key': 'sk_test_usd_specific',
                'publishable_key': 'pk_test_usd_specific',
            },
            'eur': {
                'secret_key': 'sk_test_eur_specific',
                'publishable_key': 'pk_test_eur_specific',
            },
        },
    )
    @patch('api.services.stripe_client.stripe.StripeClient')
    def test_async_client_uses_currency_specific_secret_key(self, mocked_stripe_client):
        """Для EUR должен использоваться eur-specific secret key."""
        get_stripe_client_for_currency('eur')

        mocked_stripe_client.assert_called_once()
        self.assertEqual(
            mocked_stripe_client.call_args.args[0],
            'sk_test_eur_specific',
        )

    @override_settings(
        STRIPE_API_VERSION='2026-02-25.clover',
        STRIPE_CURRENCY_KEYPAIRS={
            'usd': {
                'secret_key': 'sk_test_default',
                'publishable_key': 'pk_test_default',
            },
            'eur': {
                'secret_key': 'sk_test_eur_specific',
                'publishable_key': 'pk_test_eur_specific',
            },
        },
    )
    def test_publishable_key_uses_currency_specific_value(self):
        """Страница EUR-товара должна получить eur-specific publishable key."""
        self.assertEqual(
            get_publishable_key_for_currency('eur'),
            'pk_test_eur_specific',
        )

    @override_settings(
        STRIPE_API_VERSION='2026-02-25.clover',
        STRIPE_CURRENCY_KEYPAIRS={
            'usd': {
                'secret_key': 'sk_test_shared',
                'publishable_key': 'pk_test_shared',
            },
            'eur': {
                'secret_key': 'sk_test_shared',
                'publishable_key': 'pk_test_shared',
            },
        },
    )
    @patch('api.services.stripe_client.stripe.StripeClient')
    def test_sync_client_can_use_shared_keypair_for_one_account_setup(self, mocked_stripe_client):
        """При одном Stripe account обе валюты должны работать на общем keypair."""
        get_sync_stripe_client_for_currency('usd')

        mocked_stripe_client.assert_called_once()
        self.assertEqual(
            mocked_stripe_client.call_args.args[0],
            'sk_test_shared',
        )

    @override_settings(
        STRIPE_API_VERSION='2026-02-25.clover',
        STRIPE_SECRET_KEY='',
        STRIPE_PUBLISHABLE_KEY='',
        STRIPE_CURRENCY_KEYPAIRS={
            'usd': {
                'secret_key': 'sk_test_usd_only',
                'publishable_key': 'pk_test_usd_only',
            },
            'eur': {
                'secret_key': '',
                'publishable_key': '',
            },
        },
    )
    def test_missing_currency_key_raises_clear_error(self):
        """Если keypair для валюты не найден, приложение должно падать явно."""
        with self.assertRaises(ImproperlyConfigured):
            get_publishable_key_for_currency('eur')
