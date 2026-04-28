"""URL-ы приложения `api`.

Сейчас файл служит точкой подключения маршрутов приложения к корневому URLConf.
По мере реализации ТЗ здесь появятся маршруты:
- `/item/<id>`;
- `/buy/<id>`;
- `/order/<id>`;
- `/buy-order/<id>`;
- `/stripe/webhook/`.
"""

from django.urls import path

from api.views.checkout import (
    buy_item,
    buy_order,
    buy_order_payment_intent,
    checkout_cancel,
    checkout_success,
)
from api.views.docs import openapi_schema, redoc_ui, swagger_ui
from api.views.home import home
from api.views.item import item_detail, order_detail, order_payment_intent_detail
from api.views.system import health_check
from api.views.webhook import stripe_webhook

app_name = 'api'

urlpatterns = [
    # Главная страница с быстрыми входами в товары, заказы, админку и docs.
    path('', home, name='home'),
    # OpenAPI-документация: машиночитаемая схема + Swagger UI + Redoc UI.
    path('api/schema/', openapi_schema, name='openapi-schema'),
    path('api/docs/', swagger_ui, name='swagger-ui'),
    path('api/redoc/', redoc_ui, name='redoc-ui'),
    # Обязательная часть тестового задания: страница товара и endpoint запуска
    # Stripe Checkout Session для одного Item.
    path('item/<int:item_id>', item_detail, name='item-detail'),
    path('buy/<int:item_id>', buy_item, name='buy-item'),
    # Следующий обязательный вертикальный сценарий: покупка заказа, состоящего
    # из нескольких товарных позиций.
    path('order/<int:order_id>', order_detail, name='order-detail'),
    path('buy-order/<int:order_id>', buy_order, name='buy-order'),
    # Bonus-flow: отдельная страница и отдельный endpoint для Payment Intent.
    path(
        'order/<int:order_id>/payment-intent',
        order_payment_intent_detail,
        name='order-payment-intent-detail',
    ),
    path(
        'buy-order-payment-intent/<int:order_id>',
        buy_order_payment_intent,
        name='buy-order-payment-intent',
    ),
    # Эти страницы не перечислены как отдельные обязательные endpoints в ТЗ,
    # но нужны для завершенного redirect flow после Checkout.
    path('success', checkout_success, name='checkout-success'),
    path('cancel', checkout_cancel, name='checkout-cancel'),
    # Webhook нужен как серверный источник истины по финальному результату
    # оплаты и для синхронизации локальной базы со Stripe.
    path('stripe/webhook/', stripe_webhook, name='stripe-webhook'),
    # Технический endpoint для healthcheck-проб и быстрой диагностики после деплоя.
    path('health/', health_check, name='health-check'),
]
