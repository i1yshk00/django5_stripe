"""Админка для моделей, связанных со скидками и налогами.

Сущности `Discount` и `Tax` тесно связаны между собой по смыслу: обе отвечают
за корректное представление ценообразования в Stripe Checkout. Поэтому их
админ-описания удобно держать в одном модуле.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from api.models import Discount, Tax


@admin.register(Discount)
class DiscountAdmin(ModelAdmin):
    """Кастомная админка для скидок, связанных с Stripe Coupon.

    Администратор должен видеть не только внутреннее имя скидки, но и внешний
    идентификатор купона в Stripe, потому что именно он участвует в payload
    Checkout Session.
    """

    list_display = (
        'id',
        'name',
        'stripe_coupon_id',
        'discount_type',
        'value',
        'currency',
        'active',
        'created_at',
    )
    list_filter = ('discount_type', 'currency', 'active', 'created_at')
    search_fields = ('name', 'stripe_coupon_id')
    ordering = ('name',)
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    'name',
                    'stripe_coupon_id',
                    'discount_type',
                    'value',
                    'currency',
                    'active',
                )
            },
        ),
        (
            'Служебная информация',
            {'fields': ('created_at', 'updated_at')},
        ),
    )


@admin.register(Tax)
class TaxAdmin(ModelAdmin):
    """Кастомная админка для налоговых ставок, связанных с Stripe Tax Rate.

    Здесь мы храним и редактируем локальное представление налоговых ставок,
    синхронизированных с объектами `Tax Rate` в Stripe.
    """

    list_display = (
        'id',
        'name',
        'stripe_tax_rate_id',
        'percentage',
        'inclusive',
        'active',
        'created_at',
    )
    list_filter = ('inclusive', 'active', 'created_at')
    search_fields = ('name', 'stripe_tax_rate_id')
    ordering = ('name',)
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    'name',
                    'stripe_tax_rate_id',
                    'percentage',
                    'inclusive',
                    'active',
                )
            },
        ),
        (
            'Служебная информация',
            {'fields': ('created_at', 'updated_at')},
        ),
    )
