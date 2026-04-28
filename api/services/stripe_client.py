"""Фабрика и вспомогательные функции для инициализации Stripe client.

Теперь модуль действительно маршрутизирует Stripe keypair по валюте:
- `USD` может использовать собственные `sk/pk`;
- `EUR` может использовать отдельные `sk/pk`;
- если валютные ключи не заданы, включается fallback на общий keypair.

Это позволяет одновременно поддержать:
1. бонусный пункт ТЗ про разные keypair по валютам;
2. реальный проектный режим, где один Stripe account обслуживает обе валюты.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import stripe


# Простой словарь вместо `functools.lru_cache`: позволяет инвалидировать кеш
# из тестов через `_clear_stripe_client_cache`, иначе значения, прочитанные
# при первом обращении, остались бы "замороженными" даже после
# `override_settings`.
_async_client_cache: dict[tuple[str, str, str], stripe.StripeClient] = {}
_sync_client_cache: dict[tuple[str, str, str], stripe.StripeClient] = {}


def _clear_stripe_client_cache() -> None:
    """Сбрасывает оба кеша Stripe-клиентов.

    Используется тестами в `setUp`, чтобы `override_settings(STRIPE_*)`
    действительно влияли на следующие вызовы фабрики.
    """
    _async_client_cache.clear()
    _sync_client_cache.clear()


def _normalize_currency(currency: str | None) -> str:
    """Нормализует код валюты для доступа к настройкам keypair."""
    return (currency or 'usd').lower()


def _get_currency_keypair(currency: str | None) -> dict[str, str]:
    """Возвращает keypair для конкретной валюты из Django settings.

    Структура `STRIPE_CURRENCY_KEYPAIRS` собирается в `settings/stripe.py` и
    уже учитывает fallback на общий ключ. Здесь мы только читаем готовую карту,
    чтобы service-слой не знал ничего про устройство `.env`.
    """
    normalized_currency = _normalize_currency(currency)
    keypairs = getattr(settings, 'STRIPE_CURRENCY_KEYPAIRS', {})
    configured_pair = keypairs.get(normalized_currency, {})

    if normalized_currency == 'usd':
        secret_key = configured_pair.get('secret_key') or getattr(
            settings,
            'STRIPE_USD_SECRET_KEY',
            '',
        )
        publishable_key = configured_pair.get('publishable_key') or getattr(
            settings,
            'STRIPE_USD_PUBLISHABLE_KEY',
            '',
        )
    elif normalized_currency == 'eur':
        secret_key = configured_pair.get('secret_key') or getattr(
            settings,
            'STRIPE_EUR_SECRET_KEY',
            '',
        )
        publishable_key = configured_pair.get('publishable_key') or getattr(
            settings,
            'STRIPE_EUR_PUBLISHABLE_KEY',
            '',
        )
    else:
        secret_key = configured_pair.get('secret_key', '')
        publishable_key = configured_pair.get('publishable_key', '')

    return {
        'secret_key': secret_key or getattr(settings, 'STRIPE_SECRET_KEY', ''),
        'publishable_key': publishable_key or getattr(
            settings,
            'STRIPE_PUBLISHABLE_KEY',
            '',
        ),
    }


def _validate_server_side_stripe_settings(currency: str | None = None) -> str:
    """Проверяет, что серверная конфигурация Stripe действительно задана.

    Для серверных операций проекту нужен секретный ключ для выбранной валюты.
    Это относится и к созданию Checkout Session, и к webhook-логике, и к
    административной синхронизации скидок/налогов с Stripe.

    Returns:
        Секретный ключ, который следует использовать для указанной валюты.
    """
    secret_key = _get_currency_keypair(currency).get('secret_key', '')

    if not secret_key:
        raise ImproperlyConfigured(
            (
                'Не найден Stripe secret key для валюты '
                f'"{_normalize_currency(currency)}". Проверьте '
                'STRIPE_CURRENCY_KEYPAIRS или STRIPE_SECRET_KEY.'
            )
        )

    if not getattr(settings, 'STRIPE_API_VERSION', ''):
        raise ImproperlyConfigured(
            'Не задан STRIPE_API_VERSION. Интеграция Stripe должна работать '
            'на фиксированной версии API — задайте переменную окружения явно.'
        )

    return secret_key


def _validate_publishable_key(currency: str | None = None) -> str:
    """Проверяет наличие публичного ключа для клиентского Stripe.js.

    Returns:
        Публичный ключ для выбранной валюты.
    """
    publishable_key = _get_currency_keypair(currency).get('publishable_key', '')

    if not publishable_key:
        raise ImproperlyConfigured(
            (
                'Не найден Stripe publishable key для валюты '
                f'"{_normalize_currency(currency)}". Проверьте '
                'STRIPE_CURRENCY_KEYPAIRS или STRIPE_PUBLISHABLE_KEY.'
            )
        )

    return publishable_key


def get_stripe_client_for_currency(currency: str | None = None) -> stripe.StripeClient:
    """Возвращает готовый async Stripe client для нужной валюты.

    Кеш ключуется по `(currency, secret_key, api_version)`: если в тестах через
    `override_settings` поменяли значения, следующий вызов соберет новый
    клиент, а не вернет старый из-за совпадения только по валюте.

    Args:
        currency: Валюта платежа, по которой выбирается нужный secret key.

    Returns:
        Инициализированный экземпляр `stripe.StripeClient`.
    """
    secret_key = _validate_server_side_stripe_settings(currency)
    api_version = settings.STRIPE_API_VERSION
    cache_key = (_normalize_currency(currency), secret_key, api_version)

    cached_client = _async_client_cache.get(cache_key)
    if cached_client is not None:
        return cached_client

    # `HTTPXClient` из stripe[async] позволяет вызывать `create_async(...)`
    # без оборачивания синхронных SDK-вызовов в threadpool. Это соответствует
    # нашему решению держать проект асинхронным на Uvicorn/ASGI.
    client = stripe.StripeClient(
        secret_key,
        stripe_version=api_version,
        max_network_retries=2,
        http_client=stripe.HTTPXClient(allow_sync_methods=False),
    )
    _async_client_cache[cache_key] = client
    return client


def get_sync_stripe_client_for_currency(currency: str | None = None) -> stripe.StripeClient:
    """Возвращает sync Stripe client для административных и model-level операций.

    Почему нужен отдельный sync client:
    - Django `Model.save()` работает синхронно;
    - админка Django тоже использует синхронный request cycle;
    - для автоматического создания `Coupon` и `Tax Rate` при сохранении модели
      нам нужен безопасный sync-вход в тот же Stripe API.

    Args:
        currency: Валюта, по которой выбирается нужный secret key.

    Returns:
        Инициализированный `stripe.StripeClient`, разрешающий sync-вызовы.
    """
    secret_key = _validate_server_side_stripe_settings(currency)
    api_version = settings.STRIPE_API_VERSION
    cache_key = (_normalize_currency(currency), secret_key, api_version)

    cached_client = _sync_client_cache.get(cache_key)
    if cached_client is not None:
        return cached_client

    client = stripe.StripeClient(
        secret_key,
        stripe_version=api_version,
        max_network_retries=2,
    )
    _sync_client_cache[cache_key] = client
    return client


def get_publishable_key_for_currency(currency: str | None = None) -> str:
    """Возвращает публичный ключ Stripe для браузерной инициализации.

    Args:
        currency: Валюта страницы товара или заказа.

    Returns:
        Строку вида `pk_test_...`, которая безопасно передается в шаблон.
    """
    return _validate_publishable_key(currency)
