Принято. Тогда план строим не как “сдать тестовое локально”, а как **full-featured + production-ready**, чтобы потом без переделок выкатить проект.

**Что сейчас по проекту**
- ТЗ зафиксировано в [stripe.md](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/stripe.md).
- Инфраструктурная база уже есть: [Dockerfile](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/Dockerfile), [docker-compose.yml](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/docker-compose.yml), [ci.yml](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/.github/workflows/ci.yml), пакет настроек в [django5_stripe/settings](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/django5_stripe/settings).
- Доменный код пока пустой: [api/models](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/models), [api/views](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/views), [api/services](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/services).
- Есть важная конфигурационная проблема: `BASE_DIR` в [settings.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/django5_stripe/settings/settings.py) сейчас указывает на пакет `django5_stripe`, а не на корень проекта. Это надо исправить в самом начале, иначе шаблоны, `db.sqlite3` и `staticfiles` будут жить не там.

**Пошаговый план**
1. **Стабилизировать конфиг проекта**
   - Исправить `BASE_DIR`.
   - Подключить `api.urls` в корневой [urls.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/django5_stripe/urls.py).
   - Добавить `STATICFILES_DIRS` для корневой [static](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/static).
   - Разделить настройки на `base/dev/prod`, оставив текущий пакет `settings`.
   - Сразу добавить production flags: `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` через env.

2. **Собрать доменную модель под весь scope**
   - `Item(name, description, price, currency)`.
   - `Order`.
   - `OrderItem(order, item, quantity, unit_price_snapshot, item_name_snapshot)`.
   - `Discount(name, stripe_coupon_id, ...)`.
   - `Tax(name, stripe_tax_rate_id, ...)`.
   - Для `Order` сразу предусмотреть `stripe_session_id`, `stripe_payment_intent_id`, `payment_status`, `checkout_mode`.
   - Хранить money как `Decimal`, а для Stripe конвертировать в minor units в сервисном слое.

3. **Сделать admin как основной backoffice**
   - Регистрация всех моделей в пакете [api/admin](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/admin).
   - Inline для `OrderItem`.
   - Фильтры по `currency`, `payment_status`, `checkout_mode`.
   - Поля `readonly` для Stripe-идентификаторов.
   - Это важно и для бонуса, и для реальной ручной проверки проекта.

4. **Собрать основной обязательный Checkout flow**
   - `GET /item/<id>`: HTML-страница товара.
   - `GET /buy/<id>`: создание `stripe.checkout.Session.create(...)`.
   - Шаблон [templates/api/item_detail.html](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/templates/api/item_detail.html).
   - JS в [static/api/js/checkout.js](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/static/api/js/checkout.js).
   - Это первая рабочая вертикаль, которая закрывает основной пункт ТЗ.

5. **Собрать Order Checkout flow**
   - `GET /order/<id>`.
   - `GET /buy-order/<id>`.
   - На стороне Stripe формировать несколько `line_items`.
   - Если у заказа товары в разных валютах, запретить смешение на уровне модели/валидации. Один заказ — одна валюта.

6. **Добавить Discount и Tax так, как этого хочет ТЗ**
   - Не считать скидку и налог только локально.
   - Для Checkout Session передавать реальные Stripe-атрибуты:
     - `discounts=[{"coupon": stripe_coupon_id}]`
     - `tax_rates=[stripe_tax_rate_id]` на line item или нужный уровень.
   - Тогда они будут отображаться в Stripe Checkout корректно.

7. **Добавить multi-currency + 2 keypair**
   - Вынести валютные настройки в отдельный конфиг, например `currency -> secret/publishable key`.
   - По `Item.currency` или `Order.currency` выбирать нужный Stripe client.
   - Это должно жить в [api/services/stripe_client.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/services/stripe_client.py), а не во views.

8. **Реализовать bonus flow через Payment Intent**
   - Не вместо Checkout Session, а рядом.
   - Отдельный endpoint и отдельная HTML-страница/режим.
   - Для тестового лучше показать, что проект поддерживает два сценария:
     - обязательный `Checkout Session`
     - bonus `Payment Intent`

9. **Добавить webhook-слой**
   - `POST /stripe/webhook/`.
   - Проверка signature.
   - Обработка минимум:
     - `checkout.session.completed`
     - `payment_intent.succeeded`
     - `payment_intent.payment_failed`
   - Обновление `Order.payment_status`.
   - Это уже часть production-ready интеграции, без неё оплата не завершена архитектурно.

10. **Сделать сервисный слой окончательно**
   - [checkout.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/services/checkout.py): сборка payload для Session / PaymentIntent.
   - [stripe_client.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/services/stripe_client.py): создание async Stripe client по валюте.
   - [webhooks.py](/Users/ilazogzin/PycharmProjects/sas/django5_stripe/api/services/webhooks.py): верификация событий и обновление домена.
   - View должны остаться тонкими.

11. **Довести проект до production-ready окружения**
   - Postgres для production и желательно для Docker-окружения.
   - `collectstatic`, WhiteNoise или внешний static host.
   - Нормальные env: `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, Stripe keys, webhook secret.
   - Health endpoint `/health/`.
   - Логирование в stdout в структурированном или хотя бы стабильном формате.
   - Старт-команда контейнера с `migrate` через entrypoint или release step.

12. **Покрыть тестами критический путь**
   - Модели: валидация валюты, запрет смешанной валюты в заказе, snapshot-логика.
   - Views: `/item/{id}`, `/buy/{id}`, `/order/{id}`, `/buy-order/{id}`.
   - Services: payload для Checkout Session и Payment Intent.
   - Webhook: успешная смена статусов.
   - Stripe SDK в тестах мокать, не ходить в сеть.

13. **Подготовить данные для быстрой проверки**
   - Fixtures / management command для demo items, order, discount, tax.
   - Скрипт создания superuser из env.
   - Это критично для удобной проверки на деплое.

14. **Финализировать README и деплой**
   - Локальный запуск.
   - Docker запуск.
   - `.env.example`.
   - Admin credentials strategy.
   - Какие тестовые Stripe карты использовать.
   - Ссылка на deployed app и admin в итоговой сдаче.

**Порядок реализации по факту**
1. config cleanup  
2. models + migrations  
3. admin  
4. basic item checkout  
5. order checkout  
6. discount/tax  
7. currency routing  
8. payment intent  
9. webhooks  
10. tests  
11. production hardening  
12. deploy + README

**Критерий готовности**
Проект считается законченным только когда:
- `Item` и `Order` оплачиваются через Checkout Session
- есть отдельный Payment Intent flow
- discount/tax видны в Stripe Checkout
- multi-currency реально выбирает разные keypair
- webhook обновляет статусы
- admin usable
- Docker/CI зелёные
- проект поднимается на проде без ручных правок кода

Следующий правильный шаг: **исправить конфиг и сразу после этого реализовать модели с миграциями**, потому что от них зависит вообще всё остальное.
