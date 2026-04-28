"""Сервис синхронизации локальных скидок и налогов с объектами Stripe.

Этот модуль отвечает за backoffice-сценарий:
- администратор создает `Discount` в локальной БД;
- приложение автоматически создает соответствующий `Coupon` в Stripe;
- администратор создает `Tax` в локальной БД;
- приложение автоматически создает соответствующий `Tax Rate` в Stripe.

Почему логика вынесена из моделей:
- модели остаются читаемыми и не знают деталей Stripe payload;
- сетевые вызовы легче тестировать через patch одного сервиса;
- если позже появятся команды синхронизации или импорт из Stripe, они смогут
  переиспользовать тот же код без дублирования.
"""

from __future__ import annotations

import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from .stripe_client import get_sync_stripe_client_for_currency

if TYPE_CHECKING:
    from api.models import Discount, Tax


def _make_idempotency_key(prefix: str) -> str:
    """Возвращает уникальный idempotency-key для Stripe write-вызова."""
    return f'{prefix}-{secrets.token_hex(16)}'


def _decimal_to_minor_units(value: Decimal) -> int:
    """Переводит денежное Decimal-значение в minor units для Stripe."""
    normalized_value = (value * Decimal('100')).quantize(
        Decimal('1'),
        rounding=ROUND_HALF_UP,
    )
    return int(normalized_value)


def build_coupon_create_params(discount: 'Discount') -> dict[str, object]:
    """Строит payload для создания Stripe Coupon по локальной модели скидки.

    Реализация опирается на официальную Stripe API Reference:
    - coupon принимает либо `percent_off`, либо `amount_off` + `currency`;
    - `duration` по умолчанию `once`, но мы задаем его явно, чтобы поведение
      было очевидным и устойчивым между окружениями.
    Источник: https://docs.stripe.com/api/coupons/create
    """
    params: dict[str, object] = {
        'name': discount.name,
        'duration': 'once',
        'metadata': {
            'local_model': 'Discount',
            'local_discount_name': discount.name,
        },
    }

    if discount.discount_type == 'percent':
        params['percent_off'] = str(discount.value)
    else:
        params['amount_off'] = _decimal_to_minor_units(discount.value)
        params['currency'] = discount.currency

    return params


def create_stripe_coupon_for_discount(discount: 'Discount') -> str:
    """Создает в Stripe Coupon и возвращает его идентификатор."""
    client = get_sync_stripe_client_for_currency(discount.currency or None)
    coupon = client.v1.coupons.create(
        params=build_coupon_create_params(discount),
        options={'idempotency_key': _make_idempotency_key('coupon-create')},
    )
    return coupon.id


def update_stripe_coupon_for_discount(discount: 'Discount') -> None:
    """Синхронизирует изменяемые поля локальной скидки с уже созданным Coupon.

    На текущей версии Stripe у Coupon безопасно обновляются `name` и `metadata`,
    а основные денежные параметры по дизайну не редактируются.
    Источник: https://docs.stripe.com/api/coupons/update
    """
    client = get_sync_stripe_client_for_currency(discount.currency or None)
    client.v1.coupons.update(
        discount.stripe_coupon_id,
        params={
            'name': discount.name,
            'metadata': {
                'local_model': 'Discount',
                'local_discount_name': discount.name,
            },
        },
    )


def build_tax_rate_create_params(tax: 'Tax') -> dict[str, object]:
    """Строит payload для создания Stripe Tax Rate.

    Для нашего тестового проекта достаточно обязательных и реально используемых
    параметров:
    - `display_name`;
    - `inclusive`;
    - `percentage`;
    - `metadata`.
    Источник: https://docs.stripe.com/billing/taxes/tax-rates
    """
    return {
        'display_name': tax.name,
        'inclusive': tax.inclusive,
        'percentage': str(tax.percentage),
        'metadata': {
            'local_model': 'Tax',
            'local_tax_name': tax.name,
        },
    }


def create_stripe_tax_rate_for_tax(tax: 'Tax') -> str:
    """Создает в Stripe Tax Rate и возвращает его идентификатор."""
    client = get_sync_stripe_client_for_currency()
    tax_rate = client.v1.tax_rates.create(
        params=build_tax_rate_create_params(tax),
        options={'idempotency_key': _make_idempotency_key('tax-rate-create')},
    )
    return tax_rate.id


def update_stripe_tax_rate_for_tax(tax: 'Tax') -> None:
    """Синхронизирует изменяемые поля локального налога с Stripe Tax Rate.

    Для существующего Tax Rate безопасно обновляем:
    - `display_name`;
    - `active`;
    - `metadata`.
    Основные расчетные параметры `percentage` и `inclusive` считаем
    неизменяемыми после создания удаленного объекта, чтобы локальная база не
    расходилась с уже созданной ставкой в Stripe.
    Источник: https://docs.stripe.com/api/tax_rates/update
    """
    client = get_sync_stripe_client_for_currency()
    client.v1.tax_rates.update(
        tax.stripe_tax_rate_id,
        params={
            'display_name': tax.name,
            'active': tax.active,
            'metadata': {
                'local_model': 'Tax',
                'local_tax_name': tax.name,
            },
        },
    )
