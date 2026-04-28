"""Конфигурация кастомной админки на базе Django Unfold.

Этот модуль отвечает только за визуальный и навигационный слой backoffice:
- брендинг админки;
- боковое меню;
- ссылки на основные разделы проекта;
- индикацию текущего окружения.

Бизнес-логика и работа с моделями здесь не размещаются. Для этого у проекта
есть отдельный admin-слой внутри `api/admin/`.
"""

import os

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def unfold_environment_callback(request):
    """Возвращает метку окружения для заголовка админки.

    Unfold умеет показывать в верхней части интерфейса компактный бейдж с
    названием текущего окружения. Это полезно, чтобы не перепутать dev и prod.

    Args:
        request: Текущий HTTP-запрос администратора.

    Returns:
        Список из двух элементов: текст бейджа и его цветовой вариант.
    """
    del request

    django_env = os.getenv('DJANGO_ENV', 'dev').lower()
    if django_env in {'prod', 'production'}:
        return ['Production', 'danger']
    return ['Development', 'info']


UNFOLD = {
    # Заголовок в теге <title> и общее имя админки.
    'SITE_TITLE': 'Stripe Backoffice',
    # Название в боковой панели.
    'SITE_HEADER': 'Stripe Backoffice',
    # Подзаголовок под названием проекта в боковой панели.
    'SITE_SUBHEADER': 'Управление товарами, заказами и Stripe',
    # Базовая ссылка по клику на бренд админки.
    'SITE_URL': '/',
    # Иконка из Material Symbols для бренда в боковой панели.
    'SITE_SYMBOL': 'payments',
    # Показываем историю изменений объектов, так как это полезно для backoffice.
    'SHOW_HISTORY': True,
    # Кнопка "View on site" нам пока не нужна, потому что сайт еще не собран.
    'SHOW_VIEW_ON_SITE': False,
    # Дополнительная кнопка "Назад" в форме редактирования.
    'SHOW_BACK_BUTTON': True,
    # Показываем текущее окружение в заголовке интерфейса.
    'ENVIRONMENT': 'django5_stripe.settings.unfold.unfold_environment_callback',
    # Главная страница админки больше не использует стандартный список моделей
    # как единственный контент. Вместо этого Unfold вызывает callback, который
    # добавляет в контекст метрики, таблицы и данные для графиков.
    'DASHBOARD_CALLBACK': 'api.admin.dashboard.dashboard_callback',
    # Настройка боковой панели и ее групп навигации.
    'SIDEBAR': {
        # Оставляем поиск по моделям и приложениям включенным.
        'show_search': True,
        # Командную палитру пока не включаем, чтобы интерфейс оставался проще.
        'command_search': False,
        # Не показываем выпадающий список всех приложений поверх нашей структуры.
        'show_all_applications': False,
        'navigation': [
            {
                'title': _('Backoffice'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {
                        'title': _('Дашборд'),
                        'icon': 'dashboard',
                        'link': reverse_lazy('admin:index'),
                    },
                    {
                        'title': _('Товары'),
                        'icon': 'inventory_2',
                        'link': reverse_lazy('admin:api_item_changelist'),
                    },
                    {
                        'title': _('Заказы'),
                        'icon': 'receipt_long',
                        'link': reverse_lazy('admin:api_order_changelist'),
                    },
                    {
                        'title': _('Позиции заказа'),
                        'icon': 'list_alt',
                        'link': reverse_lazy('admin:api_orderitem_changelist'),
                    },
                    {
                        'title': _('Скидки'),
                        'icon': 'sell',
                        'link': reverse_lazy('admin:api_discount_changelist'),
                    },
                    {
                        'title': _('Налоги'),
                        'icon': 'percent',
                        'link': reverse_lazy('admin:api_tax_changelist'),
                    },
                ],
            },
            {
                'title': _('Система'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {
                        'title': _('Пользователи'),
                        'icon': 'group',
                        'link': reverse_lazy('admin:auth_user_changelist'),
                    },
                    {
                        'title': _('Группы'),
                        'icon': 'admin_panel_settings',
                        'link': reverse_lazy('admin:auth_group_changelist'),
                    },
                ],
            },
        ],
    },
}
