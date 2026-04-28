"""Сервисный слой для обработки входящих webhook-событий Stripe.

Этот модуль делает две вещи:
1. принимает Stripe event и переводит его в понятное локальное действие над
   моделью `Order`;
2. позволяет переиспользовать ту же логику не только из webhook endpoint-а,
   но и из success-страницы Checkout, если нужно синхронизировать заказ сразу
   после возврата пользователя из Stripe.

Главная идея здесь простая: источником истины по результату платежа является
Stripe, а локальная база должна отражать этот результат через обновление
`payment_status`, `paid_at`, `stripe_session_id` и `stripe_payment_intent_id`.
"""

from __future__ import annotations

from typing import Any

import stripe
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from api.models import Order, PaymentStatus, ProcessedStripeEvent
from api.services.stripe_client import get_stripe_client_for_currency


class InvalidStripeWebhookPayloadError(ValueError):
    """Ошибка формата или структуры входящего webhook payload от Stripe."""


class InvalidStripeWebhookSignatureError(ValueError):
    """Ошибка проверки подписи Stripe webhook."""


def _get_object_value(source: Any, key: str, default: Any = None) -> Any:
    """Извлекает значение из dict-подобного объекта или StripeObject.

    Stripe SDK может возвращать и обычные словари, и объекты с атрибутами.
    Чтобы остальная логика не дублировала проверки типов в каждом месте,
    используем единый безопасный helper.
    """
    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(key, default)

    return getattr(source, key, default)


def _get_nested_value(source: Any, *keys: str) -> Any:
    """Последовательно проходит по вложенным ключам/атрибутам объекта."""
    current = source

    for key in keys:
        current = _get_object_value(current, key)
        if current is None:
            return None

    return current


def _normalize_stripe_object_id(value: Any) -> str:
    """Приводит ссылку на Stripe object к его строковому идентификатору."""
    if value is None:
        return ''

    if isinstance(value, str):
        return value

    object_id = _get_object_value(value, 'id', '')
    return object_id or ''


async def _find_order(
    *,
    metadata_order_id: str = '',
    stripe_session_id: str = '',
    stripe_payment_intent_id: str = '',
) -> Order | None:
    """Находит локальный заказ по metadata или Stripe-идентификаторам.

    Приоритет поиска:
    1. `metadata.order_id` как самый надежный внутренний идентификатор;
    2. `stripe_session_id`, если событие относится к Checkout Session;
    3. `stripe_payment_intent_id`, если событие относится к PaymentIntent.
    """
    if metadata_order_id:
        try:
            return await Order.objects.aget(pk=int(metadata_order_id))
        except (ValueError, Order.DoesNotExist):
            return None

    if stripe_session_id:
        try:
            return await Order.objects.aget(stripe_session_id=stripe_session_id)
        except Order.DoesNotExist:
            return None

    if stripe_payment_intent_id:
        try:
            return await Order.objects.aget(
                stripe_payment_intent_id=stripe_payment_intent_id
            )
        except Order.DoesNotExist:
            return None

    return None


async def _save_order_status(
    order: Order,
    *,
    payment_status: str,
    stripe_session_id: str = '',
    stripe_payment_intent_id: str = '',
    mark_paid: bool = False,
) -> Order:
    """Обновляет заказ по результату Stripe-события.

    Args:
        order: Заказ, который нужно синхронизировать.
        payment_status: Новое внутреннее состояние заказа.
        stripe_session_id: Идентификатор Checkout Session, если доступен.
        stripe_payment_intent_id: Идентификатор PaymentIntent, если доступен.
        mark_paid: Нужно ли проставить `paid_at` текущим временем.
    """
    order.payment_status = payment_status

    if stripe_session_id:
        order.stripe_session_id = stripe_session_id

    if stripe_payment_intent_id:
        order.stripe_payment_intent_id = stripe_payment_intent_id

    if mark_paid and order.paid_at is None:
        order.paid_at = timezone.now()

    await order.asave(
        update_fields=(
            'payment_status',
            'stripe_session_id',
            'stripe_payment_intent_id',
            'paid_at',
            'updated_at',
        )
    )
    return order


async def sync_order_from_checkout_session_object(session: Any) -> Order | None:
    """Синхронизирует локальный заказ по объекту Checkout Session.

    Эта функция используется как из webhook endpoint-а, так и из success-URL,
    когда у нас уже есть `session_id` и нужно быстро подтянуть результат оплаты.
    """
    session_id = _normalize_stripe_object_id(_get_object_value(session, 'id'))
    payment_intent_id = _normalize_stripe_object_id(
        _get_object_value(session, 'payment_intent')
    )
    payment_status = _get_object_value(session, 'payment_status', '')
    status = _get_object_value(session, 'status', '')
    metadata_order_id = _get_nested_value(session, 'metadata', 'order_id') or ''

    order = await _find_order(
        metadata_order_id=metadata_order_id,
        stripe_session_id=session_id,
        stripe_payment_intent_id=payment_intent_id,
    )
    if order is None:
        return None

    if payment_status in {'paid', 'no_payment_required'}:
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.PAID,
            stripe_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
            mark_paid=True,
        )

    if status == 'expired':
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.EXPIRED,
            stripe_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
        )

    return await _save_order_status(
        order,
        payment_status=PaymentStatus.PROCESSING,
        stripe_session_id=session_id,
        stripe_payment_intent_id=payment_intent_id,
    )


async def sync_order_from_checkout_session_id(
    session_id: str,
    *,
    currency: str | None = None,
) -> Order | None:
    """Получает Checkout Session из Stripe API и синхронизирует локальный заказ.

    Функция полезна для success-страницы: если пользователь успешно вернулся из
    Stripe, проект может подтянуть актуальный статус даже до настройки webhook.
    При этом webhook все равно остается обязательным и более надежным каналом.
    """
    if not session_id:
        return None

    client = get_stripe_client_for_currency(currency)
    session = await client.v1.checkout.sessions.retrieve_async(session_id)
    return await sync_order_from_checkout_session_object(session)


async def sync_order_from_payment_intent_object(payment_intent: Any) -> Order | None:
    """Синхронизирует локальный заказ по объекту Stripe PaymentIntent."""
    payment_intent_id = _normalize_stripe_object_id(
        _get_object_value(payment_intent, 'id')
    )
    status = _get_object_value(payment_intent, 'status', '')
    metadata_order_id = _get_nested_value(payment_intent, 'metadata', 'order_id') or ''

    order = await _find_order(
        metadata_order_id=metadata_order_id,
        stripe_payment_intent_id=payment_intent_id,
    )
    if order is None:
        return None

    if status == 'succeeded':
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.PAID,
            stripe_payment_intent_id=payment_intent_id,
            mark_paid=True,
        )

    if status in {'requires_payment_method', 'canceled'}:
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.FAILED,
            stripe_payment_intent_id=payment_intent_id,
        )

    if status == 'processing':
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.PROCESSING,
            stripe_payment_intent_id=payment_intent_id,
        )

    return await _save_order_status(
        order,
        payment_status=PaymentStatus.PENDING,
        stripe_payment_intent_id=payment_intent_id,
    )


async def sync_order_from_payment_intent_id(
    payment_intent_id: str,
    *,
    currency: str | None = None,
) -> Order | None:
    """Получает PaymentIntent из Stripe API и синхронизирует локальный заказ."""
    if not payment_intent_id:
        return None

    client = get_stripe_client_for_currency(currency)
    payment_intent = await client.v1.payment_intents.retrieve_async(payment_intent_id)
    return await sync_order_from_payment_intent_object(payment_intent)


async def _handle_checkout_session_event(event_type: str, session: Any) -> Order | None:
    """Обрабатывает Stripe-события, у которых `data.object` — Checkout Session."""
    if event_type in {
        'checkout.session.completed',
        'checkout.session.async_payment_succeeded',
    }:
        return await sync_order_from_checkout_session_object(session)

    if event_type == 'checkout.session.async_payment_failed':
        session_id = _normalize_stripe_object_id(_get_object_value(session, 'id'))
        payment_intent_id = _normalize_stripe_object_id(
            _get_object_value(session, 'payment_intent')
        )
        metadata_order_id = _get_nested_value(session, 'metadata', 'order_id') or ''
        order = await _find_order(
            metadata_order_id=metadata_order_id,
            stripe_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
        )
        if order is None:
            return None

        return await _save_order_status(
            order,
            payment_status=PaymentStatus.FAILED,
            stripe_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
        )

    if event_type == 'checkout.session.expired':
        session_id = _normalize_stripe_object_id(_get_object_value(session, 'id'))
        metadata_order_id = _get_nested_value(session, 'metadata', 'order_id') or ''
        order = await _find_order(
            metadata_order_id=metadata_order_id,
            stripe_session_id=session_id,
        )
        if order is None:
            return None

        return await _save_order_status(
            order,
            payment_status=PaymentStatus.EXPIRED,
            stripe_session_id=session_id,
        )

    return None


async def _handle_payment_intent_event(event_type: str, payment_intent: Any) -> Order | None:
    """Обрабатывает Stripe-события, у которых `data.object` — PaymentIntent."""
    payment_intent_id = _normalize_stripe_object_id(_get_object_value(payment_intent, 'id'))
    metadata_order_id = _get_nested_value(payment_intent, 'metadata', 'order_id') or ''

    order = await _find_order(
        metadata_order_id=metadata_order_id,
        stripe_payment_intent_id=payment_intent_id,
    )
    if order is None:
        return None

    if event_type == 'payment_intent.succeeded':
        return await sync_order_from_payment_intent_object(payment_intent)

    if event_type == 'payment_intent.payment_failed':
        return await _save_order_status(
            order,
            payment_status=PaymentStatus.FAILED,
            stripe_payment_intent_id=payment_intent_id,
        )

    if event_type == 'payment_intent.processing':
        return await sync_order_from_payment_intent_object(payment_intent)

    return None


async def _claim_event_for_processing(event_id: str, event_type: str) -> bool:
    """Регистрирует Stripe event как обрабатываемый ровно один раз.

    Stripe гарантирует at-least-once доставку, поэтому один и тот же `event.id`
    может прийти повторно при ретраях. Уникальный constraint на `event_id`
    превращает повтор в no-op: `get_or_create` вернет `created=False`,
    и обработчик молча пропустит событие, не сдвигая повторно `paid_at`
    или статусы заказов.
    """
    if not event_id:
        # Без идентификатора корректно зафиксировать факт обработки нельзя.
        # Лучше выполнить событие, чем потерять его — но залогировать стоит.
        return True

    _, created = await ProcessedStripeEvent.objects.aget_or_create(
        event_id=event_id,
        defaults={'event_type': event_type or ''},
    )
    return created


async def handle_stripe_event(event: Any) -> Order | None:
    """Маршрутизирует Stripe event к нужному обработчику и обновляет заказ.

    Перед маршрутизацией проверяет журнал `ProcessedStripeEvent`: если событие
    уже было обработано раньше, повторная доставка от Stripe не должна
    приводить к повторным мутациям заказа.
    """
    event_type = _get_object_value(event, 'type', '')
    event_id = _get_object_value(event, 'id', '') or ''
    event_object = _get_nested_value(event, 'data', 'object')

    is_first_delivery = await _claim_event_for_processing(event_id, event_type)
    if not is_first_delivery:
        return None

    if event_type.startswith('checkout.session.'):
        return await _handle_checkout_session_event(event_type, event_object)

    if event_type.startswith('payment_intent.'):
        return await _handle_payment_intent_event(event_type, event_object)

    return None


def validate_webhook_secret(webhook_secret: str) -> None:
    """Проверяет, что секрет webhook действительно задан в конфигурации."""
    if not webhook_secret:
        raise ImproperlyConfigured(
            'Не задан STRIPE_WEBHOOK_SECRET. Нельзя безопасно обрабатывать Stripe webhook.'
        )


def construct_stripe_event_from_webhook(
    *,
    payload: bytes,
    signature: str,
    webhook_secret: str,
) -> Any:
    """Проверяет подпись Stripe webhook и возвращает верифицированный event.

    Эта функция нужна, чтобы логика проверки webhook не жила во view. Внешний
    HTTP-слой должен только достать `request.body` и заголовки, а все знания о
    Stripe-подписи и формате ошибок должны оставаться внутри service-слоя.

    Args:
        payload: Сырые байты тела webhook-запроса.
        signature: Значение заголовка `Stripe-Signature`.
        webhook_secret: Секрет подписи webhook из настроек проекта.

    Returns:
        Верифицированный Stripe event.

    Raises:
        ImproperlyConfigured: если секрет webhook не задан.
        InvalidStripeWebhookPayloadError: если Stripe прислал некорректное тело.
        InvalidStripeWebhookSignatureError: если подпись не прошла проверку.
    """
    validate_webhook_secret(webhook_secret)

    try:
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
    except ValueError as exc:
        raise InvalidStripeWebhookPayloadError(
            'Некорректный payload Stripe webhook.'
        ) from exc
    except stripe.SignatureVerificationError as exc:
        raise InvalidStripeWebhookSignatureError(
            'Некорректная подпись Stripe webhook.'
        ) from exc


async def sync_order_after_stripe_return(
    *,
    session_id: str = '',
    payment_intent_id: str = '',
    order_id: str = '',
) -> None:
    """Пытается синхронизировать заказ после возврата пользователя из Stripe.

    Success-страница служит удобным каналом ранней синхронизации для локальной
    разработки и ручного тестирования. При этом функция намеренно проглатывает
    временные Stripe-ошибки: окончательным источником истины все равно остается
    webhook, который придет независимо от того, вернулся пользователь на сайт
    или нет.

    Args:
        session_id: Идентификатор Checkout Session из query string.
        payment_intent_id: Идентификатор PaymentIntent из query string.
        order_id: Идентификатор локального заказа, если он был проброшен в URL.
    """
    order_currency = ''

    if order_id:
        try:
            order = await Order.objects.only('currency').aget(pk=order_id)
            order_currency = order.currency
        except Order.DoesNotExist:
            order_currency = ''

    if session_id:
        try:
            await sync_order_from_checkout_session_id(
                session_id,
                currency=order_currency or None,
            )
        except (stripe.StripeError, ImproperlyConfigured):
            pass

    if payment_intent_id:
        try:
            await sync_order_from_payment_intent_id(
                payment_intent_id,
                currency=order_currency or None,
            )
        except (stripe.StripeError, ImproperlyConfigured):
            pass
