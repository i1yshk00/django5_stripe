"""Админка для заказов и их позиций.

Это главный backoffice-модуль проекта. Именно здесь администратор видит:
- текущий статус оплаты;
- выбранный режим интеграции (`Checkout Session` или `Payment Intent`);
- расчетные суммы заказа;
- Stripe-идентификаторы, нужные для отладки и ручной проверки.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from api.models import Order, OrderItem

from .inlines import OrderItemInline
from .utils import format_money


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    """Админка для заказов как основного backoffice-объекта.

    В карточке заказа deliberately разделены:
    - бизнес-поля заказа;
    - расчетные суммы;
    - Stripe-метаданные;
    - служебные timestamps.

    Такое разбиение помогает быстрее читать объект при ручной проверке платежа.
    """

    list_display = (
        'id',
        'currency',
        'checkout_mode',
        'payment_status',
        'subtotal_amount_display',
        'discount_amount_display',
        'tax_amount_display',
        'total_amount_display',
        'paid_at',
        'created_at',
    )
    list_filter = (
        'currency',
        'payment_status',
        'checkout_mode',
        'created_at',
        'updated_at',
        'paid_at',
    )
    search_fields = (
        '=id',
        'stripe_session_id',
        'stripe_payment_intent_id',
        'stripe_client_secret',
    )
    list_select_related = ('discount', 'tax')
    ordering = ('-created_at', 'id')
    list_per_page = 25
    autocomplete_fields = ('discount', 'tax')
    readonly_fields = (
        'subtotal_amount_display',
        'discount_amount_display',
        'tax_amount_display',
        'total_amount_display',
        'stripe_session_id',
        'stripe_payment_intent_id',
        'stripe_client_secret',
        'paid_at',
        'created_at',
        'updated_at',
    )
    inlines = (OrderItemInline,)
    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    'currency',
                    'checkout_mode',
                    'payment_status',
                    'discount',
                    'tax',
                )
            },
        ),
        (
            'Расчетные суммы',
            {
                'fields': (
                    'subtotal_amount_display',
                    'discount_amount_display',
                    'tax_amount_display',
                    'total_amount_display',
                )
            },
        ),
        (
            'Stripe',
            {
                'fields': (
                    'stripe_session_id',
                    'stripe_payment_intent_id',
                    'stripe_client_secret',
                    'paid_at',
                )
            },
        ),
        (
            'Служебная информация',
            {'fields': ('created_at', 'updated_at')},
        ),
    )

    @admin.display(description='Сумма без скидок и налогов')
    def subtotal_amount_display(self, obj: Order) -> str:
        """Показывает subtotal заказа в формате `сумма + валюта`."""
        return format_money(obj.subtotal_amount, obj.currency)

    @admin.display(description='Сумма скидки')
    def discount_amount_display(self, obj: Order) -> str:
        """Показывает итоговую денежную величину скидки."""
        return format_money(obj.discount_amount, obj.currency)

    @admin.display(description='Сумма налога')
    def tax_amount_display(self, obj: Order) -> str:
        """Показывает рассчитанную сумму налога."""
        return format_money(obj.tax_amount, obj.currency)

    @admin.display(description='Итоговая сумма')
    def total_amount_display(self, obj: Order) -> str:
        """Показывает полную сумму заказа после скидок и налогов."""
        return format_money(obj.total_amount, obj.currency)


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    """Отдельная админка позиций заказа.

    Несмотря на наличие inline в `OrderAdmin`, отдельный changelist по позициям
    тоже полезен: он позволяет искать и аудитить конкретные строки заказа
    независимо от карточки родительского `Order`.
    """

    list_display = (
        'id',
        'order',
        'item',
        'quantity',
        'unit_price',
        'currency',
        'line_subtotal_display',
        'created_at',
    )
    list_filter = ('currency', 'created_at', 'updated_at')
    search_fields = ('=id', '=order__id', 'item__name', 'item_name')
    ordering = ('id',)
    list_per_page = 25
    autocomplete_fields = ('order', 'item')
    readonly_fields = (
        'item_name',
        'item_description',
        'unit_price',
        'currency',
        'line_subtotal_display',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    'order',
                    'item',
                    'quantity',
                )
            },
        ),
        (
            'Снимок товара',
            {
                'fields': (
                    'item_name',
                    'item_description',
                    'unit_price',
                    'currency',
                    'line_subtotal_display',
                )
            },
        ),
        (
            'Служебная информация',
            {'fields': ('created_at', 'updated_at')},
        ),
    )

    @admin.display(description='Сумма позиции')
    def line_subtotal_display(self, obj: OrderItem) -> str:
        """Показывает стоимость позиции заказа в человекочитаемом формате."""
        return format_money(obj.line_subtotal, obj.currency)
