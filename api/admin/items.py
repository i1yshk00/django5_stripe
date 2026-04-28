"""Админка каталога товаров.

В этом модуле собрана только админка модели `Item`. Выделение каталога в
отдельный файл упрощает навигацию по backoffice-коду: заказы, скидки и товары
не смешиваются в одном длинном `admin.py`.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from api.models import Item


@admin.register(Item)
class ItemAdmin(ModelAdmin):
    """Кастомная админка для каталога товаров.

    Интерфейс сделан вокруг двух задач:
    - быстро просматривать и редактировать товарный каталог;
    - сразу видеть цену в minor units, в которых сумма уйдет в Stripe.
    """

    list_display = (
        'id',
        'name',
        'price',
        'currency',
        'amount_minor_units_display',
        'created_at',
        'updated_at',
    )
    list_filter = ('currency', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    ordering = ('id',)
    list_per_page = 25
    readonly_fields = (
        'amount_minor_units_display',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    'name',
                    'description',
                    'price',
                    'currency',
                )
            },
        ),
        (
            'Stripe',
            {'fields': ('amount_minor_units_display',)},
        ),
        (
            'Служебная информация',
            {'fields': ('created_at', 'updated_at')},
        ),
    )

    @admin.display(description='Minor units')
    def amount_minor_units_display(self, obj: Item) -> int:
        """Показывает цену товара в формате, который ожидает Stripe API."""
        return obj.amount_minor_units
