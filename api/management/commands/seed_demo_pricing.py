"""Создает demo-скидки и demo-налог через реальный Stripe API.

Команду стоит запускать вручную после `migrate`:

    python manage.py seed_demo_pricing

Что делает команда:
- проверяет, что в окружении есть валидные Stripe-ключи и `STRIPE_API_VERSION`;
- создает (или находит существующие) `Coupon` и `Tax Rate` в Stripe;
- сохраняет ID этих объектов в локальных моделях `Discount` и `Tax`;
- привязывает demo-заказ `4002` к скидке и налогу для проверки в админке.

Команда идемпотентна: повторный запуск не создает дубликаты ни в Stripe,
ни в локальной БД. Если ключей нет, команда мягко выходит с понятной
диагностикой, а не падает — это удобно для CI и stage-окружений без Stripe.

Логика была изначально внутри миграций `0005`/`0006`. Теперь эти миграции
no-op, а сам seed вынесен сюда — миграции больше не зависят от внешней сети.
"""

from __future__ import annotations

from decimal import Decimal

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import Discount, Order, Tax


DEMO_PERCENT_DISCOUNT_ID = 2001
DEMO_FIXED_EUR_DISCOUNT_ID = 2002
DEMO_TAX_ID = 3001
DEMO_ORDER_WITH_PRICING_ID = 4002

# Маркер, который команда ставит в `metadata.seed_source`. По нему же ищем
# существующие объекты, чтобы не плодить дубликаты при повторных прогонах.
SEED_SOURCE_MARKERS = frozenset({
    'api.demo_pricing_seed',
    'api.migrations.0005_create_valid_pricing_seed',
})
ACTIVE_SEED_SOURCE_MARKER = 'api.demo_pricing_seed'


def _has_real_secret_key(secret_key: str) -> bool:
    """Проверяет, что ключ выглядит как реальный Stripe secret key."""
    if not secret_key:
        return False
    if 'change_me' in secret_key:
        return False
    return secret_key.startswith('sk_')


def _get_secret_key_for_currency(currency: str | None = None) -> str:
    """Возвращает подходящий Stripe secret key для запрошенной валюты."""
    if (currency or '').lower() == 'eur' and getattr(settings, 'STRIPE_EUR_SECRET_KEY', ''):
        return settings.STRIPE_EUR_SECRET_KEY
    return getattr(settings, 'STRIPE_SECRET_KEY', '')


def _build_stripe_client(currency: str | None = None) -> stripe.StripeClient | None:
    """Создает sync Stripe client или возвращает `None`, если конфиг неполный."""
    secret_key = _get_secret_key_for_currency(currency)
    api_version = getattr(settings, 'STRIPE_API_VERSION', '')

    if not _has_real_secret_key(secret_key):
        return None
    if not api_version:
        return None

    return stripe.StripeClient(
        secret_key,
        stripe_version=api_version,
        max_network_retries=2,
    )


def _has_matching_seed_source(metadata: object) -> bool:
    """Проверяет, что Stripe-объект относится к нашему demo seed."""
    if not isinstance(metadata, dict):
        return False
    return metadata.get('seed_source') in SEED_SOURCE_MARKERS


def _find_existing_coupon(client: stripe.StripeClient, *, name: str):
    """Ищет ранее созданный demo-coupon по имени и metadata-маркеру."""
    coupons = client.v1.coupons.list(params={'limit': 100})
    for coupon in coupons.data:
        if getattr(coupon, 'name', '') != name:
            continue
        if _has_matching_seed_source(getattr(coupon, 'metadata', {})):
            return coupon
    return None


def _ensure_coupon(client: stripe.StripeClient, *, name: str, create_params: dict) -> object:
    """Возвращает существующий demo-coupon или создает новый."""
    existing = _find_existing_coupon(client, name=name)
    if existing is not None:
        return existing
    return client.v1.coupons.create(params=create_params)


def _find_existing_tax_rate(client: stripe.StripeClient, *, display_name: str):
    """Ищет ранее созданный demo Tax Rate по имени и metadata-маркеру."""
    tax_rates = client.v1.tax_rates.list(params={'limit': 100, 'active': True})
    for tax_rate in tax_rates.data:
        if getattr(tax_rate, 'display_name', '') != display_name:
            continue
        if _has_matching_seed_source(getattr(tax_rate, 'metadata', {})):
            return tax_rate
    return None


def _ensure_tax_rate(client: stripe.StripeClient, *, display_name: str, create_params: dict) -> object:
    """Возвращает существующий demo Tax Rate или создает новый."""
    existing = _find_existing_tax_rate(client, display_name=display_name)
    if existing is not None:
        return existing
    return client.v1.tax_rates.create(params=create_params)


class Command(BaseCommand):
    """Создает demo Stripe Coupon/Tax Rate и привязывает их к demo-заказу."""

    help = (
        'Создает demo-скидки и demo-налог через реальный Stripe API '
        'и сохраняет их идентификаторы в локальной БД.'
    )

    def handle(self, *args, **options) -> None:
        """Запускает идемпотентный seed Stripe pricing."""
        del args, options

        percent_client = _build_stripe_client()
        eur_client = _build_stripe_client('eur')
        tax_client = _build_stripe_client()

        if percent_client is None or eur_client is None or tax_client is None:
            self.stdout.write(
                self.style.WARNING(
                    'Stripe-ключи или STRIPE_API_VERSION не заданы — пропускаем '
                    'seed demo pricing. Заполните `.env` и запустите команду снова.'
                )
            )
            return

        percent_coupon = _ensure_coupon(
            percent_client,
            name='Demo 10% Off',
            create_params={
                'name': 'Demo 10% Off',
                'duration': 'once',
                'percent_off': '10.00',
                'metadata': {
                    'local_model': 'Discount',
                    'seed_source': ACTIVE_SEED_SOURCE_MARKER,
                },
            },
        )

        eur_coupon = _ensure_coupon(
            eur_client,
            name='Demo 5 EUR Off',
            create_params={
                'name': 'Demo 5 EUR Off',
                'duration': 'once',
                'amount_off': 500,
                'currency': 'eur',
                'metadata': {
                    'local_model': 'Discount',
                    'seed_source': ACTIVE_SEED_SOURCE_MARKER,
                },
            },
        )

        tax_rate = _ensure_tax_rate(
            tax_client,
            display_name='Demo VAT 20%',
            create_params={
                'display_name': 'Demo VAT 20%',
                'inclusive': False,
                'percentage': '20.00',
                'metadata': {
                    'local_model': 'Tax',
                    'seed_source': ACTIVE_SEED_SOURCE_MARKER,
                },
            },
        )

        Discount.objects.update_or_create(
            id=DEMO_PERCENT_DISCOUNT_ID,
            defaults={
                'name': 'Demo 10% Off',
                'stripe_coupon_id': percent_coupon.id,
                'discount_type': 'percent',
                'value': Decimal('10.00'),
                'currency': '',
                'active': True,
            },
        )

        fixed_eur_discount, _ = Discount.objects.update_or_create(
            id=DEMO_FIXED_EUR_DISCOUNT_ID,
            defaults={
                'name': 'Demo 5 EUR Off',
                'stripe_coupon_id': eur_coupon.id,
                'discount_type': 'fixed',
                'value': Decimal('5.00'),
                'currency': 'eur',
                'active': True,
            },
        )

        seeded_tax, _ = Tax.objects.update_or_create(
            id=DEMO_TAX_ID,
            defaults={
                'name': 'Demo VAT 20%',
                'stripe_tax_rate_id': tax_rate.id,
                'percentage': Decimal('20.00'),
                'inclusive': False,
                'active': True,
            },
        )

        Order.objects.filter(id=DEMO_ORDER_WITH_PRICING_ID).update(
            discount_id=fixed_eur_discount.id,
            tax_id=seeded_tax.id,
        )

        self.stdout.write(
            self.style.SUCCESS(
                'Demo Stripe pricing успешно засеежен: '
                f'coupons {percent_coupon.id}, {eur_coupon.id}; '
                f'tax_rate {tax_rate.id}.'
            )
        )
