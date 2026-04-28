"""Views для приема webhook-запросов от Stripe.

Этот endpoint нужен потому, что redirect на success-страницу не является
надежным подтверждением платежа:
- пользователь может закрыть вкладку и не вернуться в приложение;
- некоторые способы оплаты подтверждаются асинхронно;
- информация о неуспешных попытках оплаты приходит именно через события Stripe.

Поэтому webhook — обязательный источник истины для финального статуса продажи.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

from api.services.webhooks import (
    InvalidStripeWebhookPayloadError,
    InvalidStripeWebhookSignatureError,
    construct_stripe_event_from_webhook,
    handle_stripe_event,
)


@csrf_exempt
async def stripe_webhook(request):
    """Принимает Stripe webhook и делегирует всю Stripe-логику service-слою.

    `csrf_exempt` обязателен: Stripe не передает CSRF-токен и cookies, поэтому
    без декоратора `CsrfViewMiddleware` будет отвергать каждый POST с 403 еще
    до проверки подписи.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    try:
        event = construct_stripe_event_from_webhook(
            payload=request.body,
            signature=request.headers.get('Stripe-Signature', ''),
            webhook_secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ImproperlyConfigured as exc:
        return HttpResponseBadRequest(str(exc))
    except InvalidStripeWebhookPayloadError as exc:
        return HttpResponseBadRequest(str(exc))
    except InvalidStripeWebhookSignatureError as exc:
        return HttpResponseBadRequest(str(exc))

    await handle_stripe_event(event)
    return HttpResponse(status=200)
