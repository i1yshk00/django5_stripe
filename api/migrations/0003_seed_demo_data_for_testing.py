"""Создает только безопасные демо-данные для ручного тестирования Stripe flow.

В старой версии seed-миграции в базу попадали placeholder-идентификаторы
объектов Stripe (`coupon_...`, `txr_...`, `cs_...`, `pi_...`). Формально это
помогало наполнить dashboard, но на новом стенде такие данные не являются
валидными для реального Stripe account пользователя.

Новая миграция оставляет только те демо-данные, которые:
- не содержат фейковых Stripe ID;
- не ломают Checkout сразу после первого `migrate`;
- позволяют проверить обязательный `/item/<id>` сценарий;
- позволяют проверить `Order` с несколькими `Item`;
- позволяют проверить мультивалютность через `USD` и `EUR`.

Сознательно не создаем демонстрационные `Discount` и `Tax`, потому что для них
нужны реальные объекты Stripe в конкретном пользовательском аккаунте. Их
корректнее создавать уже через админку после настройки ключей.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.color import no_style
from django.db import migrations


# Фиксированные ID делают ручную проверку предсказуемой:
# - `/item/1001`
# - `/item/1003`
# - `/order/4001`
# - `/order/4002`
DEMO_ITEM_IDS = (1001, 1002, 1003, 1004)
DEMO_ORDER_IDS = (4001, 4002)
DEMO_ORDER_ITEM_IDS = (5001, 5002, 5003, 5004)


def _reset_sequences(apps, schema_editor) -> None:
    """Сдвигает sequence вперед после вставки объектов с явными `id`."""
    models_to_reset = [
        apps.get_model('api', 'Item'),
        apps.get_model('api', 'Order'),
        apps.get_model('api', 'OrderItem'),
    ]

    statements = schema_editor.connection.ops.sequence_reset_sql(
        no_style(),
        models_to_reset,
    )

    for statement in statements:
        schema_editor.execute(statement)


def create_demo_data(apps, schema_editor) -> None:
    """Создает минимальный, но полезный набор демо-товаров и заказов."""
    Item = apps.get_model('api', 'Item')
    Order = apps.get_model('api', 'Order')
    OrderItem = apps.get_model('api', 'OrderItem')

    items = (
        {
            'id': 1001,
            'name': 'Stripe Demo T-Shirt',
            'description': (
                'USD-товар для проверки обязательного сценария `/item/<id>` '
                'и прямого Checkout Session flow.'
            ),
            'price': Decimal('29.90'),
            'currency': 'usd',
        },
        {
            'id': 1002,
            'name': 'Stripe Demo Mug',
            'description': (
                'Дополнительный USD-товар для заказа из нескольких позиций.'
            ),
            'price': Decimal('14.50'),
            'currency': 'usd',
        },
        {
            'id': 1003,
            'name': 'Stripe Demo Notebook',
            'description': (
                'EUR-товар для проверки мультивалютного сценария на странице '
                '`/item/<id>`.'
            ),
            'price': Decimal('18.90'),
            'currency': 'eur',
        },
        {
            'id': 1004,
            'name': 'Stripe Demo Backpack',
            'description': (
                'Дополнительный EUR-товар для демонстрационного заказа.'
            ),
            'price': Decimal('64.00'),
            'currency': 'eur',
        },
    )

    orders = (
        {
            'id': 4001,
            'currency': 'usd',
            'checkout_mode': 'checkout_session',
            'payment_status': 'draft',
            'stripe_session_id': '',
            'stripe_payment_intent_id': '',
            'stripe_client_secret': '',
            'paid_at': None,
            'discount_id': None,
            'tax_id': None,
        },
        {
            'id': 4002,
            'currency': 'eur',
            'checkout_mode': 'checkout_session',
            'payment_status': 'draft',
            'stripe_session_id': '',
            'stripe_payment_intent_id': '',
            'stripe_client_secret': '',
            'paid_at': None,
            'discount_id': None,
            'tax_id': None,
        },
    )

    order_items = (
        {
            'id': 5001,
            'order_id': 4001,
            'item_id': 1001,
            'quantity': 1,
            'item_name': 'Stripe Demo T-Shirt',
            'item_description': (
                'Первая позиция USD-заказа для Checkout Session с несколькими '
                'line_items.'
            ),
            'unit_price': Decimal('29.90'),
            'currency': 'usd',
        },
        {
            'id': 5002,
            'order_id': 4001,
            'item_id': 1002,
            'quantity': 2,
            'item_name': 'Stripe Demo Mug',
            'item_description': (
                'Вторая позиция USD-заказа для ручной проверки multi-item flow.'
            ),
            'unit_price': Decimal('14.50'),
            'currency': 'usd',
        },
        {
            'id': 5003,
            'order_id': 4002,
            'item_id': 1003,
            'quantity': 1,
            'item_name': 'Stripe Demo Notebook',
            'item_description': (
                'Первая позиция EUR-заказа для проверки мультивалютного checkout.'
            ),
            'unit_price': Decimal('18.90'),
            'currency': 'eur',
        },
        {
            'id': 5004,
            'order_id': 4002,
            'item_id': 1004,
            'quantity': 1,
            'item_name': 'Stripe Demo Backpack',
            'item_description': (
                'Вторая позиция EUR-заказа для проверки Payment Intent и '
                'Checkout Session на евро-товарах.'
            ),
            'unit_price': Decimal('64.00'),
            'currency': 'eur',
        },
    )

    for item_payload in items:
        Item.objects.update_or_create(
            id=item_payload['id'],
            defaults=item_payload,
        )

    for order_payload in orders:
        Order.objects.update_or_create(
            id=order_payload['id'],
            defaults=order_payload,
        )

    for order_item_payload in order_items:
        OrderItem.objects.update_or_create(
            id=order_item_payload['id'],
            defaults=order_item_payload,
        )

    _reset_sequences(apps, schema_editor)


class Migration(migrations.Migration):
    """Добавляет минимальные валидные демо-данные без фейковых Stripe ID."""

    dependencies = [
        ('api', '0002_create_default_admin_user'),
    ]

    operations = [
        migrations.RunPython(
            create_demo_data,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
