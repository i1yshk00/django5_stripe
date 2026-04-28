"""Программная сборка OpenAPI 3.1 спецификации проекта.

Зачем не статический YAML и не drf-spectacular:
- проект использует чистые async Django views без DRF, поэтому
  автогенерация через `drf-spectacular` потребовала бы переписывания
  всех endpoint-ов на DRF APIView;
- статический YAML легко расходится с реальностью при переименовании URL.

Решение — программно собрать OpenAPI dict в Python, подтягивая пути через
`reverse()`. Это даёт:
- один источник правды для документации;
- автоматическое обновление путей при изменении `urls.py`;
- валидную OpenAPI 3.1 спецификацию для Swagger UI / Redoc / любых
  внешних потребителей.
"""

from __future__ import annotations

from django.urls import reverse


# Sentinel-значение для подстановки в `<int:>`-конвертер при `reverse()`.
# Должно быть валидным целым числом, чтобы pass URL-валидацию, и при этом
# уникальным в строке URL, чтобы простая замена не задела другие сегменты.
_OPENAPI_INT_SENTINEL = 9999999999


def _resolve_path(reverse_name: str, *, kwarg: str | None = None) -> str:
    """Возвращает строку URL с OpenAPI-плейсхолдером `{kwarg}` вместо реального ID.

    Django `<int:>`-конвертер при `reverse()` требует целочисленный аргумент,
    поэтому используем sentinel-число и заменяем его на `{kwarg}` в результате.

    Args:
        reverse_name: namespace + url name, например `api:buy-item`.
        kwarg: имя единственного параметра пути (`item_id` или `order_id`).
    """
    if kwarg is None:
        return reverse(reverse_name)

    url = reverse(reverse_name, kwargs={kwarg: _OPENAPI_INT_SENTINEL})
    return url.replace(str(_OPENAPI_INT_SENTINEL), '{' + kwarg + '}')


def build_openapi_schema() -> dict[str, object]:
    """Собирает полную OpenAPI 3.1 спецификацию проекта.

    Returns:
        Словарь, который можно сериализовать в JSON и отдать Swagger UI.
    """
    return {
        'openapi': '3.1.0',
        'info': {
            'title': 'django5_stripe API',
            'version': '0.1.0',
            'description': (
                'Stripe Checkout Session, Payment Intent flow и webhook-обработка '
                'для Django 5 + ASGI + Stripe.'
            ),
            'contact': {
                'name': 'Project repository',
                'url': 'https://github.com/',
            },
        },
        'servers': [
            {'url': '/', 'description': 'Текущий хост'},
        ],
        'tags': [
            {'name': 'Checkout', 'description': 'Запуск Stripe Checkout Session по товару или заказу.'},
            {'name': 'Payment Intent', 'description': 'Запуск Stripe Payment Intent flow для заказа.'},
            {'name': 'HTML pages', 'description': 'HTML-страницы для пользователя.'},
            {'name': 'Webhook', 'description': 'Прием webhook-событий от Stripe.'},
            {'name': 'System', 'description': 'Технические endpoint-ы для деплоя и мониторинга.'},
        ],
        'paths': {
            _resolve_path('api:item-detail', kwarg='item_id'): {
                'get': {
                    'tags': ['HTML pages'],
                    'summary': 'HTML-страница товара с кнопкой Buy',
                    'description': (
                        'Рендерит HTML-страницу с описанием товара, ценой и кнопкой '
                        '"Купить". По нажатию JS делает `fetch /buy/{item_id}` и '
                        'перенаправляет на Stripe Checkout через '
                        '`stripe.redirectToCheckout({sessionId})`.'
                    ),
                    'parameters': [_path_int_param('item_id', 'Идентификатор товара')],
                    'responses': {
                        '200': {
                            'description': 'HTML-страница товара',
                            'content': {'text/html': {'schema': {'type': 'string'}}},
                        },
                        '404': _ref_response('NotFound'),
                    },
                },
            },
            _resolve_path('api:buy-item', kwarg='item_id'): {
                'get': {
                    'tags': ['Checkout'],
                    'summary': 'Создать Stripe Checkout Session для товара',
                    'description': (
                        'Создает Stripe Checkout Session по выбранному товару, '
                        'локальный `Order` под прямую покупку, и возвращает '
                        '`session.id` для дальнейшего `stripe.redirectToCheckout`.'
                    ),
                    'parameters': [_path_int_param('item_id', 'Идентификатор товара')],
                    'responses': {
                        '200': {
                            'description': 'Stripe Checkout Session создан',
                            'content': {
                                'application/json': {
                                    'schema': {'$ref': '#/components/schemas/CheckoutSessionId'},
                                    'example': {'id': 'cs_test_a1B2c3D4e5'},
                                },
                            },
                        },
                        '404': _ref_response('NotFound'),
                        '502': _ref_response('StripeError'),
                    },
                },
            },
            _resolve_path('api:order-detail', kwarg='order_id'): {
                'get': {
                    'tags': ['HTML pages'],
                    'summary': 'HTML-страница заказа',
                    'parameters': [_path_int_param('order_id', 'Идентификатор заказа')],
                    'responses': {
                        '200': {
                            'description': 'HTML-страница заказа',
                            'content': {'text/html': {'schema': {'type': 'string'}}},
                        },
                        '404': _ref_response('NotFound'),
                    },
                },
            },
            _resolve_path('api:buy-order', kwarg='order_id'): {
                'get': {
                    'tags': ['Checkout'],
                    'summary': 'Создать Stripe Checkout Session для заказа',
                    'description': (
                        'Создает Stripe Checkout Session с несколькими `line_items`, '
                        'применяет скидку и налог, привязанные к заказу, и возвращает '
                        '`session.id`.'
                    ),
                    'parameters': [_path_int_param('order_id', 'Идентификатор заказа')],
                    'responses': {
                        '200': {
                            'description': 'Stripe Checkout Session создан',
                            'content': {
                                'application/json': {
                                    'schema': {'$ref': '#/components/schemas/CheckoutSessionId'},
                                    'example': {'id': 'cs_test_order_xyz'},
                                },
                            },
                        },
                        '400': _ref_response('BadRequest'),
                        '404': _ref_response('NotFound'),
                        '502': _ref_response('StripeError'),
                    },
                },
            },
            _resolve_path('api:order-payment-intent-detail', kwarg='order_id'): {
                'get': {
                    'tags': ['HTML pages'],
                    'summary': 'HTML-страница заказа для оплаты через Payment Intent',
                    'parameters': [_path_int_param('order_id', 'Идентификатор заказа')],
                    'responses': {
                        '200': {
                            'description': 'HTML-страница c Stripe Payment Element',
                            'content': {'text/html': {'schema': {'type': 'string'}}},
                        },
                        '404': _ref_response('NotFound'),
                    },
                },
            },
            _resolve_path('api:buy-order-payment-intent', kwarg='order_id'): {
                'get': {
                    'tags': ['Payment Intent'],
                    'summary': 'Создать или переиспользовать Stripe Payment Intent',
                    'description': (
                        'Возвращает `client_secret` для инициализации Stripe Payment Element. '
                        'Если у заказа уже есть активный PaymentIntent в подходящем статусе, '
                        'reuse предпочтительнее, чем создание нового объекта.'
                    ),
                    'parameters': [_path_int_param('order_id', 'Идентификатор заказа')],
                    'responses': {
                        '200': {
                            'description': 'Payment Intent создан или переиспользован',
                            'content': {
                                'application/json': {
                                    'schema': {'$ref': '#/components/schemas/PaymentIntentPayload'},
                                    'example': {
                                        'payment_intent_id': 'pi_test_abc',
                                        'client_secret': 'pi_test_abc_secret_xyz',
                                        'return_url': 'http://localhost:8000/success?order_id=1&payment_flow=payment_intent',
                                    },
                                },
                            },
                        },
                        '400': _ref_response('BadRequest'),
                        '404': _ref_response('NotFound'),
                        '502': _ref_response('StripeError'),
                    },
                },
            },
            _resolve_path('api:stripe-webhook'): {
                'post': {
                    'tags': ['Webhook'],
                    'summary': 'Прием Stripe webhook-событий',
                    'description': (
                        'Принимает события Stripe (`checkout.session.*`, `payment_intent.*`), '
                        'проверяет подпись через `Stripe-Signature`, защищен от replay '
                        'через журнал `ProcessedStripeEvent`. Endpoint должен быть '
                        'недоступен для CSRF-проверки (`@csrf_exempt`).'
                    ),
                    'parameters': [
                        {
                            'name': 'Stripe-Signature',
                            'in': 'header',
                            'required': True,
                            'description': 'Подпись Stripe webhook.',
                            'schema': {'type': 'string'},
                        }
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/StripeEvent'},
                            },
                        },
                    },
                    'responses': {
                        '200': {'description': 'Событие обработано или дубликат проигнорирован.'},
                        '400': {
                            'description': 'Подпись невалидна или payload некорректен.',
                            'content': {'text/plain': {'schema': {'type': 'string'}}},
                        },
                        '405': {'description': 'Метод не поддерживается.'},
                    },
                },
            },
            _resolve_path('api:checkout-success'): {
                'get': {
                    'tags': ['HTML pages'],
                    'summary': 'Страница успешной оплаты',
                    'parameters': [
                        {'name': 'session_id', 'in': 'query', 'required': False, 'schema': {'type': 'string'}},
                        {'name': 'payment_intent', 'in': 'query', 'required': False, 'schema': {'type': 'string'}},
                        {'name': 'order_id', 'in': 'query', 'required': False, 'schema': {'type': 'string'}},
                    ],
                    'responses': {
                        '200': {
                            'description': 'HTML success page',
                            'content': {'text/html': {'schema': {'type': 'string'}}},
                        },
                    },
                },
            },
            _resolve_path('api:checkout-cancel'): {
                'get': {
                    'tags': ['HTML pages'],
                    'summary': 'Страница отмены оплаты',
                    'responses': {
                        '200': {
                            'description': 'HTML cancel page',
                            'content': {'text/html': {'schema': {'type': 'string'}}},
                        },
                    },
                },
            },
            _resolve_path('api:health-check'): {
                'get': {
                    'tags': ['System'],
                    'summary': 'Health-check',
                    'description': 'Проверяет доступность приложения и БД.',
                    'responses': {
                        '200': {
                            'description': 'Приложение и БД работают',
                            'content': {
                                'application/json': {
                                    'schema': {'$ref': '#/components/schemas/HealthOk'},
                                    'example': {'status': 'ok', 'database': 'ok'},
                                },
                            },
                        },
                        '503': {
                            'description': 'Приложение работает, но БД недоступна',
                            'content': {
                                'application/json': {
                                    'schema': {'$ref': '#/components/schemas/HealthError'},
                                },
                            },
                        },
                    },
                },
            },
        },
        'components': {
            'schemas': {
                'CheckoutSessionId': {
                    'type': 'object',
                    'required': ['id'],
                    'properties': {
                        'id': {
                            'type': 'string',
                            'description': 'Stripe Checkout Session id (`cs_test_...` или `cs_live_...`).',
                            'example': 'cs_test_a1B2c3D4e5',
                        },
                    },
                },
                'PaymentIntentPayload': {
                    'type': 'object',
                    'required': ['payment_intent_id', 'client_secret', 'return_url'],
                    'properties': {
                        'payment_intent_id': {'type': 'string', 'example': 'pi_test_abc'},
                        'client_secret': {'type': 'string', 'example': 'pi_test_abc_secret_xyz'},
                        'return_url': {'type': 'string', 'format': 'uri'},
                    },
                },
                'StripeEvent': {
                    'type': 'object',
                    'description': 'Сырое событие Stripe в формате официального API.',
                    'properties': {
                        'id': {'type': 'string', 'example': 'evt_1ABC2def3GHI4jkl'},
                        'type': {
                            'type': 'string',
                            'example': 'checkout.session.completed',
                            'description': (
                                'Поддерживаются события `checkout.session.*` и `payment_intent.*`.'
                            ),
                        },
                        'data': {'type': 'object'},
                    },
                },
                'HealthOk': {
                    'type': 'object',
                    'required': ['status', 'database'],
                    'properties': {
                        'status': {'type': 'string', 'enum': ['ok']},
                        'database': {'type': 'string', 'enum': ['ok']},
                    },
                },
                'HealthError': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string'},
                        'database': {'type': 'string'},
                        'error': {'type': 'string'},
                    },
                },
                'Error': {
                    'type': 'object',
                    'properties': {
                        'error': {'type': 'string'},
                        'details': {'type': 'string'},
                    },
                },
            },
            'responses': {
                'NotFound': {
                    'description': 'Объект не найден.',
                    'content': {'text/html': {'schema': {'type': 'string'}}},
                },
                'BadRequest': {
                    'description': 'Некорректный запрос (например, пустой заказ).',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'},
                        },
                    },
                },
                'StripeError': {
                    'description': 'Ошибка на стороне Stripe или конфигурации интеграции.',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'},
                        },
                    },
                },
            },
        },
    }


def _path_int_param(name: str, description: str) -> dict[str, object]:
    """Сахар для path-параметра типа integer."""
    return {
        'name': name,
        'in': 'path',
        'required': True,
        'description': description,
        'schema': {'type': 'integer', 'minimum': 1},
    }


def _ref_response(name: str) -> dict[str, str]:
    """Сахар для `$ref` на компонент `responses`."""
    return {'$ref': f'#/components/responses/{name}'}
