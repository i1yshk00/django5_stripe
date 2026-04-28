"""View домашней страницы проекта.

На главной странице собраны быстрые входы для проверки тестового задания:
- список demo-товаров (`/item/<id>` — обязательный сценарий ТЗ);
- список demo-заказов (Checkout Session и Payment Intent flow);
- админка Django Unfold;
- OpenAPI-документация (Swagger UI и Redoc);
- системные endpoint-ы (health-check, webhook).

Страница не требует аутентификации, потому что demo-стенд должен быть
сразу же осмотрен ревьюером без логина.
"""

from __future__ import annotations

from django.template.response import TemplateResponse
from django.urls import reverse

from api.models import Item, Order


async def home(request):
    """Рендерит главную страницу с быстрыми входами в проект.

    Запросы к `Item` и `Order` ограничены 8 объектами — этого достаточно
    для demo, и страница остается легкой даже на нагруженных стендах.
    """
    items = [
        item async for item in Item.objects.order_by('id')[:8]
    ]
    orders = [
        order async for order in (
            Order.objects.select_related('discount', 'tax')
            .prefetch_related('order_items')
            .order_by('-created_at', 'id')[:8]
        )
    ]

    quick_links = [
        {
            'title': 'Админка Django',
            'description': 'Backoffice на django-unfold. Логин/пароль: admin / admin12345.',
            'url': reverse('admin:index'),
            'badge': 'admin',
        },
        {
            'title': 'Swagger UI',
            'description': 'Интерактивная документация OpenAPI 3.1.',
            'url': reverse('api:swagger-ui'),
            'badge': 'docs',
        },
        {
            'title': 'Redoc',
            'description': 'Альтернативный UI для той же OpenAPI-спецификации.',
            'url': reverse('api:redoc-ui'),
            'badge': 'docs',
        },
        {
            'title': 'OpenAPI schema (JSON)',
            'description': 'Сырая OpenAPI 3.1 спецификация в JSON.',
            'url': reverse('api:openapi-schema'),
            'badge': 'json',
        },
        {
            'title': 'Health-check',
            'description': 'Проверка приложения и БД для liveness/readiness проб.',
            'url': reverse('api:health-check'),
            'badge': 'system',
        },
    ]

    return TemplateResponse(
        request,
        'api/home.html',
        {
            'items': items,
            'orders': orders,
            'quick_links': quick_links,
            'webhook_url': reverse('api:stripe-webhook'),
        },
    )
