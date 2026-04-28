"""Views для отображения пользовательских HTML-страниц.

На текущем этапе здесь живут три страницы:
- `/item/<id>` для прямой покупки товара через Checkout Session;
- `/order/<id>` для hosted Checkout оплаты заказа;
- `/order/<id>/payment-intent` для bonus-flow на Stripe Payment Intent.
"""

from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import reverse

from api.models import Item, Order
from api.services.stripe_client import get_publishable_key_for_currency


async def item_detail(request, item_id: int):
    """Рендерит HTML-страницу товара с кнопкой запуска Stripe Checkout.

    Args:
        request: Входящий HTTP-запрос.
        item_id: Идентификатор товара.

    Returns:
        `TemplateResponse` со страницей товара.
    """
    try:
        item = await Item.objects.aget(pk=item_id)
    except Item.DoesNotExist as exc:
        raise Http404('Товар не найден.') from exc

    return TemplateResponse(
        request,
        'api/item_detail.html',
        {
            'item': item,
            'buy_url': reverse('api:buy-item', args=[item.pk]),
            'stripe_publishable_key': get_publishable_key_for_currency(item.currency),
        },
    )


async def order_detail(request, order_id: int):
    """Рендерит HTML-страницу заказа с запуском Checkout Session.

    На этой странице пользователь видит все позиции заказа, итоговую сумму,
    а также примененные скидки и налоги, если они уже привязаны к заказу.
    """
    try:
        order = await (
            Order.objects.select_related('discount', 'tax')
            .prefetch_related('order_items')
            .aget(pk=order_id)
        )
    except Order.DoesNotExist as exc:
        raise Http404('Заказ не найден.') from exc

    return TemplateResponse(
        request,
        'api/order_detail.html',
        {
            'order': order,
            'buy_url': reverse('api:buy-order', args=[order.pk]),
            'payment_intent_page_url': reverse(
                'api:order-payment-intent-detail',
                args=[order.pk],
            ),
            'stripe_publishable_key': get_publishable_key_for_currency(order.currency),
        },
    )


async def order_payment_intent_detail(request, order_id: int):
    """Рендерит отдельную страницу оплаты заказа через Payment Intent.

    Здесь пользователь остается внутри нашего интерфейса, а не уходит на hosted
    Checkout страницу Stripe. Сам PaymentIntent создается отдельным endpoint-ом,
    чтобы GET-страница оставалась максимально легкой и предсказуемой.
    """
    try:
        order = await (
            Order.objects.select_related('discount', 'tax')
            .prefetch_related('order_items')
            .aget(pk=order_id)
        )
    except Order.DoesNotExist as exc:
        raise Http404('Заказ не найден.') from exc

    return TemplateResponse(
        request,
        'api/order_payment_intent.html',
        {
            'order': order,
            'create_payment_intent_url': reverse(
                'api:buy-order-payment-intent',
                args=[order.pk],
            ),
            'stripe_publishable_key': get_publishable_key_for_currency(order.currency),
        },
    )
