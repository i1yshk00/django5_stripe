"""Inline-компоненты админки приложения `api`."""

from django.contrib import admin
from unfold.admin import TabularInline

from api.models import OrderItem

from .utils import format_money


class OrderItemInline(TabularInline):
    """Inline-редактор позиций заказа внутри карточки Order.

    Используем Unfold `TabularInline`, чтобы интерфейс inline-позиций выглядел
    нативно в новой кастомной админке.
    """

    # Inline работает с моделью-связкой между заказом и товаром.
    model = OrderItem
    extra = 1
    autocomplete_fields = ('item',)
    show_change_link = True
    # Вкладочный режим делает форму заказа компактнее, особенно когда у заказа
    # будет много позиций и дополнительные Stripe-поля.
    tab = True
    fields = (
        'item',
        'quantity',
        'item_name',
        'unit_price',
        'currency',
        'line_subtotal_display',
    )
    readonly_fields = (
        'item_name',
        'unit_price',
        'currency',
        'line_subtotal_display',
    )
    verbose_name = 'Позиция заказа'
    verbose_name_plural = 'Позиции заказа'

    @admin.display(description='Сумма позиции')
    def line_subtotal_display(self, obj: OrderItem) -> str:
        """Показывает рассчитанную стоимость позиции заказа."""
        if not obj or not obj.pk:
            return 'Будет рассчитано после сохранения'
        return format_money(obj.line_subtotal, obj.currency)
