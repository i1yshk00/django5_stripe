"""Контекст и вычисления для главной страницы backoffice-дашборда.

Этот модуль держит всю dashboard-логику отдельно от:
- `settings/unfold.py`, где живет только конфигурация Unfold;
- `api/admin/*.py`, где регистрируются модели и их `ModelAdmin`.

Такое разделение полезно по двум причинам:
1. главная страница админки превращается в самостоятельный read-only слой
   аналитики, а не в набор случайных вычислений внутри шаблона;
2. при дальнейшем росте проекта сюда можно безболезненно добавлять новые
   графики, KPI и operational-виджеты.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html

from api.models import CheckoutMode, Currency, Discount, Item, Order, PaymentStatus, Tax

from .utils import format_money


# Цветовые варианты бейджей статусов. Сами классы в шаблоне выбираются через
# стандартный helper `unfold/helpers/label.html`, а здесь мы держим только
# семантическое сопоставление бизнес-статуса и визуального акцента.
PAYMENT_STATUS_VARIANTS = {
    PaymentStatus.DRAFT: 'default',
    PaymentStatus.PENDING: 'warning',
    PaymentStatus.PROCESSING: 'info',
    PaymentStatus.PAID: 'success',
    PaymentStatus.FAILED: 'danger',
    PaymentStatus.CANCELED: 'default',
    PaymentStatus.EXPIRED: 'warning',
}


def _format_datetime(value) -> str:
    """Форматирует дату и время в компактный человекочитаемый вид.

    Args:
        value: Объект даты/времени Django или `None`.

    Returns:
        Локализованную строку для отображения в dashboard-таблицах.
    """
    if value is None:
        return '—'

    return date_format(timezone.localtime(value), 'd.m.Y H:i')


def _is_placeholder_or_empty(value: str, expected_prefix: str) -> bool:
    """Проверяет, выглядит ли настройка как незаполненный placeholder.

    Для dashboard важно не просто вывести строку из settings, а дать быстрый
    operational-сигнал: реально ли сконфигурирован Stripe, или приложение все
    еще живет на шаблонных значениях `.env.example`.
    """
    if not value:
        return True

    if 'change_me' in value:
        return True

    return not value.startswith(expected_prefix)


def _render_text_link(url: str, text: str) -> str:
    """Строит безопасную HTML-ссылку в стиле Unfold-таблиц."""
    return format_html(
        (
            '<a href="{}" class="font-medium text-primary-600 '
            'hover:text-primary-500 dark:text-primary-400 '
            'dark:hover:text-primary-300">{}</a>'
        ),
        url,
        text,
    )


def _render_label(text: str, variant: str) -> str:
    """Строит компактный цветовой бейдж в стиле Unfold.

    Dashboard активно использует визуальные статусы. Формировать их на стороне
    Python удобнее, чем собирать HTML кусками прямо в таблицах шаблона.
    """
    variant_classes = {
        'info': 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
        'danger': 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
        'warning': 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400',
        'success': 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
        'primary': 'bg-primary-100 text-primary-700 dark:bg-primary-500/20 dark:text-primary-400',
        'default': 'bg-base-500/8 text-base-700 dark:bg-base-500/20 dark:text-base-200',
    }

    return format_html(
        (
            '<span class="inline-block font-semibold rounded-default text-[11px] '
            'uppercase whitespace-nowrap h-6 leading-6 px-2 {}">{}</span>'
        ),
        variant_classes.get(variant, variant_classes['default']),
        text,
    )


def _build_status_counts() -> list[dict[str, object]]:
    """Собирает статистику заказов по внутреннему статусу оплаты.

    Returns:
        Список словарей в фиксированном порядке `PaymentStatus.choices`, чтобы
        и таблица, и график, и прогресс-бары показывали одинаковую шкалу.
    """
    counts_by_status = {
        item['payment_status']: item['total']
        for item in Order.objects.values('payment_status').annotate(total=Count('id'))
    }
    total_orders = Order.objects.count()
    items: list[dict[str, object]] = []

    for status_value, status_label in PaymentStatus.choices:
        count = counts_by_status.get(status_value, 0)
        percent = round((count / total_orders) * 100, 1) if total_orders else 0
        items.append(
            {
                'value': status_value,
                'label': status_label,
                'count': count,
                'percent': percent,
                'variant': PAYMENT_STATUS_VARIANTS.get(status_value, 'default'),
            }
        )

    return items


def _build_status_chart(status_items: list[dict[str, object]]) -> tuple[str, str]:
    """Готовит данные и опции для bar chart со статусами заказов.

    Unfold уже подтягивает `Chart.js` и умеет рендерить графики из JSON-строки
    через компонент `unfold/components/chart/bar.html`. Поэтому здесь задача
    сводится к сборке компактного конфигурационного payload.
    """
    chart_data = {
        'labels': [item['label'] for item in status_items],
        'datasets': [
            {
                'label': 'Количество заказов',
                'data': [item['count'] for item in status_items],
                'backgroundColor': [
                    'rgba(148, 163, 184, 0.70)',
                    'rgba(245, 158, 11, 0.70)',
                    'rgba(59, 130, 246, 0.70)',
                    'rgba(16, 185, 129, 0.70)',
                    'rgba(239, 68, 68, 0.70)',
                    'rgba(100, 116, 139, 0.70)',
                    'rgba(236, 72, 153, 0.70)',
                ],
                'borderColor': [
                    'rgba(148, 163, 184, 1)',
                    'rgba(245, 158, 11, 1)',
                    'rgba(59, 130, 246, 1)',
                    'rgba(16, 185, 129, 1)',
                    'rgba(239, 68, 68, 1)',
                    'rgba(100, 116, 139, 1)',
                    'rgba(236, 72, 153, 1)',
                ],
                'borderWidth': 1,
                'borderRadius': 8,
                'maxBarThickness': 36,
            }
        ],
    }
    chart_options = {
        'plugins': {
            'legend': {'display': False},
        },
        'scales': {
            'x': {
                'grid': {'display': False},
            },
            'y': {
                'beginAtZero': True,
                'ticks': {'precision': 0},
            },
        },
    }

    return json.dumps(chart_data), json.dumps(chart_options)


def _build_revenue_by_currency() -> list[dict[str, object]]:
    """Считает локальную выручку по валютам на основе оплаченных заказов.

    В текущей модели итоговая сумма заказа не денормализована в отдельное поле,
    а считается через свойства `Order`. Для dashboard это допустимо: объем данных
    тестового проекта небольшой, а читаемость модели важнее преждевременной
    оптимизации. Если проект вырастет, здесь стоит перейти на сохраненный
    `total_amount_snapshot` в самом заказе.
    """
    paid_orders = (
        Order.objects.filter(payment_status=PaymentStatus.PAID)
        .select_related('discount', 'tax')
        .prefetch_related('order_items')
    )
    revenue = {
        Currency.USD: {
            'currency': 'USD',
            'orders_count': 0,
            'total_amount': Decimal('0.00'),
        },
        Currency.EUR: {
            'currency': 'EUR',
            'orders_count': 0,
            'total_amount': Decimal('0.00'),
        },
    }

    for order in paid_orders:
        bucket = revenue[order.currency]
        bucket['orders_count'] += 1
        bucket['total_amount'] += order.total_amount

    for currency_value in revenue:
        revenue[currency_value]['formatted_total'] = format_money(
            Order.quantize_amount(revenue[currency_value]['total_amount']),
            currency_value,
        )

    return list(revenue.values())


def _build_summary_cards(status_items: list[dict[str, object]]) -> list[dict[str, str]]:
    """Формирует верхний ряд KPI-карточек dashboard."""
    order_count = Order.objects.count()
    paid_count = next(
        (item['count'] for item in status_items if item['value'] == PaymentStatus.PAID),
        0,
    )
    paid_share = round((paid_count / order_count) * 100) if order_count else 0
    active_discounts = Discount.objects.filter(active=True).count()
    active_taxes = Tax.objects.filter(active=True).count()

    return [
        {
            'title': 'Товары',
            'value': str(Item.objects.count()),
            'description': 'Товаров доступно в каталоге',
            'icon': 'inventory_2',
            'href': reverse('admin:api_item_changelist'),
        },
        {
            'title': 'Заказы',
            'value': str(order_count),
            'description': 'Всего заказов в локальной базе',
            'icon': 'receipt_long',
            'href': reverse('admin:api_order_changelist'),
        },
        {
            'title': 'Оплачено',
            'value': str(paid_count),
            'description': f'{paid_share}% заказов успешно оплачены',
            'icon': 'paid',
            'href': reverse('admin:api_order_changelist') + '?payment_status__exact=paid',
        },
        {
            'title': 'Правила',
            'value': str(active_discounts + active_taxes),
            'description': f'{active_discounts} скидок и {active_taxes} налогов активны',
            'icon': 'tune',
            'href': reverse('admin:api_discount_changelist'),
        },
    ]


def _build_quick_actions() -> list[dict[str, str]]:
    """Возвращает набор быстрых действий для верхней панели dashboard."""
    return [
        {
            'title': 'Новый товар',
            'url': reverse('admin:api_item_add'),
            'icon': 'add_box',
            'variant': 'primary',
        },
        {
            'title': 'Новый заказ',
            'url': reverse('admin:api_order_add'),
            'icon': 'add_shopping_cart',
            'variant': 'default',
        },
        {
            'title': 'Новая скидка',
            'url': reverse('admin:api_discount_add'),
            'icon': 'sell',
            'variant': 'default',
        },
        {
            'title': 'Новый налог',
            'url': reverse('admin:api_tax_add'),
            'icon': 'percent',
            'variant': 'default',
        },
    ]


def _build_recent_orders_table() -> dict[str, object]:
    """Готовит данные таблицы последних заказов для главной страницы."""
    recent_orders = list(
        Order.objects.select_related('discount', 'tax')
        .prefetch_related('order_items')
        .order_by('-created_at')[:5]
    )

    return {
        'headers': ['Заказ', 'Статус', 'Режим', 'Итог', 'Создан'],
        'rows': [
            [
                _render_text_link(
                    reverse('admin:api_order_change', args=[order.pk]),
                    f'Заказ #{order.pk}',
                ),
                _render_label(
                    order.get_payment_status_display(),
                    PAYMENT_STATUS_VARIANTS.get(order.payment_status, 'default'),
                ),
                order.get_checkout_mode_display(),
                format_money(order.total_amount, order.currency),
                _format_datetime(order.created_at),
            ]
            for order in recent_orders
        ],
    }


def _build_recent_items_table() -> dict[str, object]:
    """Готовит данные таблицы последних товаров каталога."""
    recent_items = list(Item.objects.order_by('-created_at')[:5])

    return {
        'headers': ['Товар', 'Цена', 'Minor units', 'Обновлен'],
        'rows': [
            [
                _render_text_link(
                    reverse('admin:api_item_change', args=[item.pk]),
                    item.name,
                ),
                format_money(item.price, item.currency),
                item.amount_minor_units,
                _format_datetime(item.updated_at),
            ]
            for item in recent_items
        ],
    }


def _build_stripe_configuration() -> list[dict[str, str]]:
    """Собирает operational-информацию о состоянии Stripe-конфига."""
    secret_key_ready = not _is_placeholder_or_empty(settings.STRIPE_SECRET_KEY, 'sk_')
    publishable_key_ready = not _is_placeholder_or_empty(
        settings.STRIPE_PUBLISHABLE_KEY,
        'pk_',
    )
    domain_configured = bool(settings.DOMAIN_URL)
    checkout_sessions_count = Order.objects.filter(
        checkout_mode=CheckoutMode.CHECKOUT_SESSION
    ).count()
    payment_intents_count = Order.objects.filter(
        checkout_mode=CheckoutMode.PAYMENT_INTENT
    ).count()

    return [
        {
            'label': 'Секретный ключ',
            'value': 'Настроен' if secret_key_ready else 'Не настроен',
            'variant': 'success' if secret_key_ready else 'danger',
            'as_badge': True,
        },
        {
            'label': 'Публичный ключ',
            'value': 'Настроен' if publishable_key_ready else 'Не настроен',
            'variant': 'success' if publishable_key_ready else 'danger',
            'as_badge': True,
        },
        {
            'label': 'Stripe API version',
            'value': settings.STRIPE_API_VERSION,
            'variant': 'info',
            'as_badge': False,
        },
        {
            'label': 'DOMAIN_URL',
            'value': settings.DOMAIN_URL if domain_configured else 'Не задан',
            'variant': 'info' if domain_configured else 'warning',
            'as_badge': False,
        },
        {
            'label': 'Checkout Session',
            'value': str(checkout_sessions_count),
            'variant': 'primary',
            'as_badge': True,
        },
        {
            'label': 'Payment Intent',
            'value': str(payment_intents_count),
            'variant': 'primary',
            'as_badge': True,
        },
    ]


def dashboard_callback(request, context: dict[str, object]) -> dict[str, object]:
    """Добавляет в стандартный admin index данные для кастомного dashboard.

    Args:
        request: Текущий HTTP-запрос администратора.
        context: Базовый контекст, который уже подготовил `UnfoldAdminSite`.

    Returns:
        Расширенный словарь контекста для шаблона `templates/admin/index.html`.
    """
    del request

    status_items = _build_status_counts()
    status_chart_data, status_chart_options = _build_status_chart(status_items)

    context.update(
        {
            'dashboard_last_updated': _format_datetime(timezone.now()),
            'dashboard_summary_cards': _build_summary_cards(status_items),
            'dashboard_quick_actions': _build_quick_actions(),
            'dashboard_status_items': status_items,
            'dashboard_status_chart_data': status_chart_data,
            'dashboard_status_chart_options': status_chart_options,
            'dashboard_recent_orders_table': _build_recent_orders_table(),
            'dashboard_recent_items_table': _build_recent_items_table(),
            'dashboard_revenue_by_currency': _build_revenue_by_currency(),
            'dashboard_stripe_configuration': _build_stripe_configuration(),
        }
    )

    return context
