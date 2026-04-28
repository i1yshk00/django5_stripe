"""Нормализует демо-данные после пересборки миграций.

Зачем нужна отдельная миграция:
- на чистой базе `0003` уже создаст правильный seed;
- на существующей локальной базе могут лежать старые placeholder-данные из
  прежней версии проекта, потому что имена `0001/0002/0003` сохранились и
  Django считает их уже примененными;
- эта миграция доводит обе ситуации до одинакового конечного состояния.

В результате в базе остаются только безопасные demo-объекты:
- товары `1001-1004`;
- заказы `4001-4002`;
- позиции заказа `5001-5004`;
- без фейковых `coupon/tax/session/payment_intent` идентификаторов.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.color import no_style
from django.db import migrations


def _reset_sequences(apps, schema_editor) -> None:
    """Сдвигает sequence вперед после фиксированных ID и удаления старых строк."""
    models_to_reset = [
        apps.get_model('api', 'Item'),
        apps.get_model('api', 'Discount'),
        apps.get_model('api', 'Tax'),
        apps.get_model('api', 'Order'),
        apps.get_model('api', 'OrderItem'),
    ]

    statements = schema_editor.connection.ops.sequence_reset_sql(
        no_style(),
        models_to_reset,
    )

    for statement in statements:
        schema_editor.execute(statement)


def normalize_demo_seed_data(apps, schema_editor) -> None:
    """Удаляет старые placeholder-данные и восстанавливает валидный demo-seed."""
    Item = apps.get_model('api', 'Item')
    Discount = apps.get_model('api', 'Discount')
    Tax = apps.get_model('api', 'Tax')
    Order = apps.get_model('api', 'Order')
    OrderItem = apps.get_model('api', 'OrderItem')

    # Сначала убираем старые демонстрационные объекты, которые больше не считаем
    # валидными для Stripe-проверки на новом стенде.
    OrderItem.objects.filter(id__in=[5005, 5006]).delete()
    Order.objects.filter(id__in=[4003, 4004]).delete()
    Discount.objects.filter(id__in=[2001, 2002]).delete()
    Tax.objects.filter(id=3001).delete()

    # Затем гарантируем корректный набор товаров.
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
    """Приводит старый и новый seed к одному валидному состоянию."""

    dependencies = [
        ('api', '0003_seed_demo_data_for_testing'),
    ]

    operations = [
        migrations.RunPython(
            normalize_demo_seed_data,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
