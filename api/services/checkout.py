"""Сервис для сборки Stripe Checkout и Payment Intent payload.

На текущем состоянии проекта сервис уже покрывает два checkout-сценария:
- прямую покупку одного `Item`;
- покупку `Order`, содержащего несколько `OrderItem`.

Важно, что Stripe-логика остается вне views:
- view только получает HTTP-запрос и отдает HTTP-ответ;
- service знает, как превратить доменные модели в payload Stripe;
- client factory знает, как инициализировать Stripe SDK.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from decimal import Decimal

from django.conf import settings
from django.urls import reverse

from api.models import CheckoutMode, Item, Order, OrderItem, PaymentStatus

from .stripe_client import get_stripe_client_for_currency


def _make_idempotency_key(prefix: str) -> str:
    """Возвращает уникальный idempotency-key для Stripe write-вызова.

    Stripe SDK при network-retry повторно отправляет запрос с тем же
    `Idempotency-Key`, и Stripe гарантирует, что мутация выполнится только
    один раз. Без явного ключа SDK генерирует новый на каждой попытке —
    при таймаутах это потенциально создает дубликаты Session/PaymentIntent.
    Источник: https://docs.stripe.com/api/idempotent_requests
    """
    return f'{prefix}-{secrets.token_hex(16)}'


def _build_absolute_url(path: str) -> str:
    """Склеивает внешний `DOMAIN_URL` и внутренний путь приложения.

    Args:
        path: Абсолютный путь внутри Django, например `/success`.

    Returns:
        Полный URL, который можно передавать в Stripe как `success_url` или
        `cancel_url`.
    """
    return f'{settings.DOMAIN_URL}{path}'


def _build_success_url(*, item_id: int | None = None, order_id: int | None = None) -> str:
    """Собирает success-URL для возврата со Stripe Checkout.

    В URL дополнительно пробрасывается идентификатор сущности, чтобы success-
    страница могла при необходимости показать, за какой именно товар или заказ
    пользователь только что платил.
    """
    success_path = reverse('api:checkout-success')
    query_parts = ['session_id={CHECKOUT_SESSION_ID}']

    if item_id is not None:
        query_parts.append(f'item_id={item_id}')

    if order_id is not None:
        query_parts.append(f'order_id={order_id}')

    return f'{_build_absolute_url(success_path)}?{"&".join(query_parts)}'


def _build_cancel_url(*, item_id: int | None = None, order_id: int | None = None) -> str:
    """Собирает cancel-URL для возврата пользователя без завершения оплаты."""
    cancel_path = reverse('api:checkout-cancel')
    query_parts: list[str] = []

    if item_id is not None:
        query_parts.append(f'item_id={item_id}')

    if order_id is not None:
        query_parts.append(f'order_id={order_id}')

    if not query_parts:
        return _build_absolute_url(cancel_path)

    return f'{_build_absolute_url(cancel_path)}?{"&".join(query_parts)}'


def _build_payment_intent_return_url(order_id: int) -> str:
    """Собирает `return_url` для Stripe Payment Element / Payment Intent flow.

    В этот URL Stripe может вернуть пользователя после подтверждения оплаты или
    после прохождения дополнительной аутентификации. Мы заранее включаем туда
    `order_id`, чтобы success-страница могла синхронизировать и показать
    именно тот заказ, для которого был создан PaymentIntent.
    """
    success_path = reverse('api:checkout-success')
    return (
        f'{_build_absolute_url(success_path)}'
        f'?order_id={order_id}&payment_flow=payment_intent'
    )


def _build_product_data(name: str, description: str | None = None) -> dict[str, str]:
    """Строит `product_data` для inline price_data Stripe Checkout."""
    product_data = {'name': name}

    if description:
        product_data['description'] = description

    return product_data


def build_item_checkout_session_params(
    item: Item,
    *,
    order: Order | None = None,
) -> dict[str, object]:
    """Собирает payload для создания Stripe Checkout Session по товару.

    Args:
        item: Товар, который пользователь покупает напрямую через `/buy/<id>`.
        order: Локальный заказ, созданный под прямую покупку одного товара.
            Если передан, его идентификатор включается в metadata и в URL
            возврата, чтобы после оплаты приложение могло синхронизировать
            состояние продажи с локальной базой.

    Returns:
        Словарь параметров, совместимый с `checkout.sessions.create`.
    """
    payload: dict[str, object] = {
        'mode': 'payment',
        'success_url': _build_success_url(
            item_id=item.pk,
            order_id=order.pk if order else None,
        ),
        'cancel_url': _build_cancel_url(
            item_id=item.pk,
            order_id=order.pk if order else None,
        ),
        'line_items': [
            {
                'quantity': 1,
                'price_data': {
                    'currency': item.currency,
                    'unit_amount': item.amount_minor_units,
                    'product_data': _build_product_data(
                        item.name,
                        item.description,
                    ),
                },
            }
        ],
        'metadata': {
            'item_id': str(item.pk),
            'entity_type': 'item',
        },
    }

    if order is not None:
        payload['client_reference_id'] = str(order.pk)
        payload['metadata']['order_id'] = str(order.pk)

    return payload


async def create_checkout_session_for_item(item: Item, *, order: Order | None = None):
    """Создает Stripe Checkout Session для одиночного товара.

    Args:
        item: Товар, выбранный пользователем для прямой покупки.
        order: Локальный заказ, созданный под этот checkout flow.

    Returns:
        Объект Stripe Session, из которого view затем берет `session.id`.
    """
    client = get_stripe_client_for_currency(item.currency)
    session_params = build_item_checkout_session_params(item, order=order)
    return await client.v1.checkout.sessions.create_async(
        params=session_params,
        options={'idempotency_key': _make_idempotency_key('item-session')},
    )


def _build_order_line_items(order_items: Iterable[OrderItem], tax_rate_id: str | None = None) -> list[dict[str, object]]:
    """Преобразует позиции заказа в `line_items` Stripe Checkout.

    Args:
        order_items: Итерируемый набор заранее загруженных `OrderItem`.
        tax_rate_id: Идентификатор Stripe Tax Rate, который нужно применить ко
            всем позициям заказа.

    Returns:
        Список line items для `checkout.sessions.create`.
    """
    line_items: list[dict[str, object]] = []

    for order_item in order_items:
        line_item: dict[str, object] = {
            'quantity': order_item.quantity,
            'price_data': {
                'currency': order_item.currency,
                'unit_amount': int(
                    Order.quantize_amount(order_item.unit_price) * 100
                ),
                'product_data': _build_product_data(
                    order_item.item_name,
                    order_item.item_description,
                ),
            },
            'metadata': {
                'order_item_id': str(order_item.pk),
                'order_id': str(order_item.order_id),
            },
        }

        if tax_rate_id:
            line_item['tax_rates'] = [tax_rate_id]

        line_items.append(line_item)

    return line_items


def build_order_checkout_session_params(order: Order) -> dict[str, object]:
    """Собирает payload для Stripe Checkout Session по заказу.

    Перед вызовом этой функции заказ должен быть загружен вместе с `order_items`
    через `prefetch_related`, чтобы сборка payload оставалась чисто in-memory и
    не делала скрытых синхронных ORM-запросов из async view.
    """
    order_items = list(order.order_items.all())

    if not order_items:
        raise ValueError('Нельзя создать Checkout Session для пустого заказа.')

    params: dict[str, object] = {
        'mode': 'payment',
        'client_reference_id': str(order.pk),
        'success_url': _build_success_url(order_id=order.pk),
        'cancel_url': _build_cancel_url(order_id=order.pk),
        'line_items': _build_order_line_items(
            order_items,
            tax_rate_id=order.tax.stripe_tax_rate_id if order.tax_id else None,
        ),
        'metadata': {
            'order_id': str(order.pk),
            'entity_type': 'order',
        },
    }

    if order.discount_id:
        params['discounts'] = [{'coupon': order.discount.stripe_coupon_id}]

    return params


async def create_checkout_session_for_order(order: Order):
    """Создает Stripe Checkout Session для заказа из нескольких позиций."""
    client = get_stripe_client_for_currency(order.currency)
    session_params = build_order_checkout_session_params(order)
    return await client.v1.checkout.sessions.create_async(
        params=session_params,
        options={'idempotency_key': _make_idempotency_key(f'order-{order.pk}-session')},
    )


async def _mark_order_as_pending_checkout_session(order: Order, session_id: str) -> Order:
    """Сохраняет в заказе данные о запущенном Checkout Session flow.

    Эта логика вынесена в service-слой, чтобы:
    - view не управлял платежным состоянием вручную;
    - оба checkout-сценария (`Item` и `Order`) обновляли заказ одинаково;
    - дальнейшие изменения правил статусов не пришлось дублировать по нескольким
      endpoint-ам.

    Args:
        order: Локальный заказ, для которого уже создан Stripe Checkout Session.
        session_id: Идентификатор Stripe Checkout Session.

    Returns:
        Обновленный объект `Order`.
    """
    order.checkout_mode = CheckoutMode.CHECKOUT_SESSION
    order.payment_status = PaymentStatus.PENDING
    order.stripe_session_id = session_id
    await order.asave(
        update_fields=(
            'checkout_mode',
            'payment_status',
            'stripe_session_id',
            'updated_at',
        )
    )
    return order


async def _mark_order_as_failed_payment_start(
    order: Order,
    *,
    checkout_mode: str,
) -> Order:
    """Фиксирует неуспешную попытку старта платежного сценария.

    Зачем это нужно:
    - заказ не должен "зависать" в `draft`, если Stripe Session или
      PaymentIntent вообще не удалось создать;
    - локальная БД должна отражать сам факт неуспешной попытки запуска оплаты;
    - последующая аналитика и админка должны видеть такие случаи явно.

    Args:
        order: Локальный заказ, для которого не удалось стартовать оплату.
        checkout_mode: Режим оплаты, в котором произошла ошибка.

    Returns:
        Обновленный заказ со статусом `failed`.
    """
    order.checkout_mode = checkout_mode
    order.payment_status = PaymentStatus.FAILED
    await order.asave(
        update_fields=(
            'checkout_mode',
            'payment_status',
            'updated_at',
        )
    )
    return order


async def create_order_for_item_purchase(item: Item) -> Order:
    """Создает локальный заказ под прямую покупку одного товара.

    Зачем это нужно:
    - любая продажа в проекте должна иметь локальную запись в БД;
    - единая модель `Order` позволяет одинаково учитывать и прямую покупку
      товара, и checkout по заранее собранному заказу;
    - webhook-слой может обновлять один и тот же доменный объект независимо
      от того, как именно пользователь начал оплату.

    Args:
        item: Товар, который пользователь выбрал на странице `/item/<id>`.

    Returns:
        Созданный заказ со статусом ожидания оплаты и одной позицией.
    """
    order = await Order.objects.acreate(
        currency=item.currency,
        checkout_mode=CheckoutMode.CHECKOUT_SESSION,
        payment_status=PaymentStatus.DRAFT,
    )
    await OrderItem.objects.acreate(
        order=order,
        item=item,
        quantity=1,
    )
    return order


async def start_checkout_session_for_item_purchase(item: Item):
    """Полностью запускает Checkout Session flow для прямой покупки товара.

    В отличие от низкоуровневой функции `create_checkout_session_for_item`,
    этот orchestration helper делает весь необходимый набор действий:
    1. создает локальный `Order` для учета продажи;
    2. создает Checkout Session в Stripe;
    3. переводит заказ в состояние ожидания оплаты и сохраняет `session_id`.

    Args:
        item: Товар, выбранный пользователем на странице `/item/<id>`.

    Returns:
        Stripe Session, которую затем можно отдать frontend-слою.
    """
    order = await create_order_for_item_purchase(item)

    try:
        session = await create_checkout_session_for_item(item, order=order)
    except Exception:
        # Даже если Stripe Session не была создана, локальный заказ уже успел
        # появиться. Сохраняем явный `failed`, чтобы попытка оплаты не терялась
        # и не выглядела как незавершенный черновик.
        await _mark_order_as_failed_payment_start(
            order,
            checkout_mode=CheckoutMode.CHECKOUT_SESSION,
        )
        raise

    await _mark_order_as_pending_checkout_session(order, session.id)
    return session


async def start_checkout_session_for_order(order: Order):
    """Полностью запускает Checkout Session flow для уже существующего заказа.

    Args:
        order: Заказ с одной или несколькими позициями, загруженный вместе с
            `order_items`, а при необходимости и с `discount`/`tax`.

    Returns:
        Stripe Session, созданная для оплаты заказа.
    """
    try:
        session = await create_checkout_session_for_order(order)
    except Exception:
        await _mark_order_as_failed_payment_start(
            order,
            checkout_mode=CheckoutMode.CHECKOUT_SESSION,
        )
        raise

    await _mark_order_as_pending_checkout_session(order, session.id)
    return session


def _decimal_amount_to_minor_units(value: Decimal) -> int:
    """Переводит итоговую сумму заказа в minor units для PaymentIntent."""
    return int(Order.quantize_amount(value) * 100)


def build_order_payment_intent_params(order: Order) -> dict[str, object]:
    """Собирает payload для Stripe PaymentIntent по заказу.

    В отличие от Checkout Session здесь Stripe не получает детализацию line
    items, скидок и налогов как отдельные объекты интерфейса. Вместо этого мы
    создаем PaymentIntent на итоговую сумму `Order.total_amount`, которую уже
    предварительно посчитали на доменном слое.
    """
    order_items = list(order.order_items.all())

    if not order_items:
        raise ValueError('Нельзя создать PaymentIntent для пустого заказа.')

    amount = _decimal_amount_to_minor_units(order.total_amount)
    if amount <= 0:
        raise ValueError('Сумма PaymentIntent должна быть больше нуля.')

    return {
        'amount': amount,
        'currency': order.currency,
        'description': f'Оплата заказа #{order.pk}',
        'automatic_payment_methods': {
            'enabled': True,
        },
        'metadata': {
            'order_id': str(order.pk),
            'entity_type': 'order',
            'payment_flow': 'payment_intent',
        },
    }


async def create_payment_intent_for_order(order: Order):
    """Создает новый Stripe PaymentIntent для заказа."""
    client = get_stripe_client_for_currency(order.currency)
    payment_intent_params = build_order_payment_intent_params(order)
    return await client.v1.payment_intents.create_async(
        params=payment_intent_params,
        options={'idempotency_key': _make_idempotency_key(f'order-{order.pk}-pi')},
    )


async def get_or_create_payment_intent_for_order(order: Order) -> dict[str, str]:
    """Возвращает существующий или создает новый PaymentIntent для заказа.

    Мы стараемся не плодить новые PaymentIntent на каждый refresh страницы.
    Если у заказа уже есть активный `stripe_payment_intent_id` и сохраненный
    `stripe_client_secret`, reuse этого состояния предпочтительнее.
    """
    if (
        order.checkout_mode == CheckoutMode.PAYMENT_INTENT
        and order.stripe_payment_intent_id
        and order.stripe_client_secret
        and order.payment_status in {
            PaymentStatus.DRAFT,
            PaymentStatus.PENDING,
            PaymentStatus.PROCESSING,
            PaymentStatus.FAILED,
        }
    ):
        return {
            'payment_intent_id': order.stripe_payment_intent_id,
            'client_secret': order.stripe_client_secret,
            'return_url': _build_payment_intent_return_url(order.pk),
        }

    try:
        payment_intent = await create_payment_intent_for_order(order)
    except Exception:
        await _mark_order_as_failed_payment_start(
            order,
            checkout_mode=CheckoutMode.PAYMENT_INTENT,
        )
        raise

    order.checkout_mode = CheckoutMode.PAYMENT_INTENT
    order.payment_status = PaymentStatus.PENDING
    order.stripe_payment_intent_id = payment_intent.id
    order.stripe_client_secret = payment_intent.client_secret
    await order.asave(
        update_fields=(
            'checkout_mode',
            'payment_status',
            'stripe_payment_intent_id',
            'stripe_client_secret',
            'updated_at',
        )
    )

    return {
        'payment_intent_id': payment_intent.id,
        'client_secret': payment_intent.client_secret,
        'return_url': _build_payment_intent_return_url(order.pk),
    }


async def start_payment_intent_checkout_for_order(order: Order) -> dict[str, str]:
    """Запускает Payment Intent flow для заказа через единый service-entrypoint.

    Сейчас эта функция делегирует работу в `get_or_create_payment_intent_for_order`,
    но отдельная точка входа полезна архитектурно:
    - view вызывает понятную верхнеуровневую операцию домена;
    - детали reuse существующего PaymentIntent остаются внутри service-слоя;
    - дальнейшие изменения Payment Intent flow не потребуют правок во view.

    Args:
        order: Заказ, который нужно оплатить через Payment Element.

    Returns:
        JSON-совместимый payload с `payment_intent_id`, `client_secret` и
        `return_url`.
    """
    return await get_or_create_payment_intent_for_order(order)
