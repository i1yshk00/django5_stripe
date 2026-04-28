"""Views для запуска оплаты через Stripe.

Сейчас модуль покрывает три платежных сценария:
- `GET /buy/<id>` для одного товара через Checkout Session;
- `GET /buy-order/<id>` для заказа через Checkout Session;
- `GET /buy-order-payment-intent/<id>` для заказа через Payment Intent.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.template.response import TemplateResponse

import stripe

from api.models import Item, Order
from api.services.checkout import (
    start_checkout_session_for_item_purchase,
    start_checkout_session_for_order,
    start_payment_intent_checkout_for_order,
)
from api.services.webhooks import (
    sync_order_after_stripe_return,
)


def _build_checkout_error_payload(exc: Exception) -> dict[str, str]:
    """Нормализует текст ошибки для JSON-ответа frontend-слою.

    В debug-режиме полезно видеть больше деталей, чтобы быстрее исправлять
    конфигурацию или payload. В production пользователю лучше отдавать только
    безопасное и нейтральное сообщение.
    """
    if settings.DEBUG:
        return {
            'error': 'Не удалось создать Stripe Checkout Session.',
            'details': str(exc),
        }

    return {
        'error': 'Не удалось запустить оплату. Попробуйте еще раз позже.',
    }


async def buy_item(request, item_id: int):
    """Создает Checkout Session по товару и возвращает `session.id`.

    Args:
        request: Входящий HTTP-запрос. Поддерживается только `GET`.
        item_id: Идентификатор покупаемого товара.

    Returns:
        `JsonResponse` вида `{"id": "cs_test_..."}`.

    Важное поведение:
    - весь orchestration flow живет в service-слое;
    - view только получает товар, делегирует запуск оплаты и возвращает `id`;
    - локальный `Order`, Stripe Session и перевод заказа в `pending`
      создаются внутри `api.services.checkout`.
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    try:
        item = await Item.objects.aget(pk=item_id)
    except Item.DoesNotExist as exc:
        raise Http404('Товар не найден.') from exc

    try:
        session = await start_checkout_session_for_item_purchase(item)
    except (stripe.StripeError, ImproperlyConfigured) as exc:
        return JsonResponse(_build_checkout_error_payload(exc), status=502)

    return JsonResponse({'id': session.id})


async def buy_order(request, order_id: int):
    """Создает Checkout Session по заказу и сохраняет Stripe session id.

    После загрузки заказа view делегирует orchestration service-слою. Именно
    service:
    - собирает Stripe payload;
    - создает Checkout Session;
    - переводит заказ в `pending`;
    - сохраняет `stripe_session_id` до прихода webhook.
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    try:
        order = await (
            Order.objects.select_related('discount', 'tax')
            .prefetch_related('order_items')
            .aget(pk=order_id)
        )
    except Order.DoesNotExist as exc:
        raise Http404('Заказ не найден.') from exc

    try:
        session = await start_checkout_session_for_order(order)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except (stripe.StripeError, ImproperlyConfigured) as exc:
        return JsonResponse(_build_checkout_error_payload(exc), status=502)

    return JsonResponse({'id': session.id})


async def buy_order_payment_intent(request, order_id: int):
    """Создает или переиспользует PaymentIntent для заказа.

    Endpoint возвращает `client_secret`, который затем используется на
    отдельной Payment Intent странице для инициализации Stripe Payment Element.
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    try:
        order = await (
            Order.objects.select_related('discount', 'tax')
            .prefetch_related('order_items')
            .aget(pk=order_id)
        )
    except Order.DoesNotExist as exc:
        raise Http404('Заказ не найден.') from exc

    try:
        payment_intent_payload = await start_payment_intent_checkout_for_order(order)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except (stripe.StripeError, ImproperlyConfigured) as exc:
        return JsonResponse(
            {
                'error': 'Не удалось создать Stripe Payment Intent.',
                'details': str(exc) if settings.DEBUG else '',
            },
            status=502,
        )

    return JsonResponse(payment_intent_payload)


async def checkout_success(request):
    """Показывает страницу успешного завершения Checkout flow.

    View только читает query-параметры и передает их в service-слой для
    best-effort синхронизации. Все знания о том, как именно найти и обновить
    заказ по Stripe-идентификаторам, остаются в `api.services.webhooks`.
    """
    session_id = request.GET.get('session_id', '')
    payment_intent_id = request.GET.get('payment_intent', '') or request.GET.get(
        'payment_intent_id',
        '',
    )
    order_id = request.GET.get('order_id', '')
    await sync_order_after_stripe_return(
        session_id=session_id,
        payment_intent_id=payment_intent_id,
        order_id=order_id,
    )

    return TemplateResponse(
        request,
        'api/success.html',
        {
            'session_id': session_id,
            'payment_intent_id': payment_intent_id,
            'payment_flow': request.GET.get('payment_flow', ''),
            'payment_intent_status': request.GET.get('payment_intent_status', ''),
            'item_id': request.GET.get('item_id', ''),
            'order_id': order_id,
        },
    )


async def checkout_cancel(request):
    """Показывает страницу отмены Checkout flow."""
    return TemplateResponse(
        request,
        'api/cancel.html',
        {
            'item_id': request.GET.get('item_id', ''),
            'order_id': request.GET.get('order_id', ''),
        },
    )
