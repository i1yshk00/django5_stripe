# django5_stripe

Тестовый backend-проект на Django 5.2, ASGI/Uvicorn и Stripe.

Проект уже поддерживает:
- `Checkout Session` для `Item` и `Order`;
- `Payment Intent` flow для `Order`;
- webhook-синхронизацию статусов оплаты с защитой от replay по `event.id`;
- идемпотентные Stripe write-вызовы (`Idempotency-Key` на каждый create);
- кастомную admin-панель на `django-unfold`;
- multi-currency routing для `USD` и `EUR`;
- production-ready Docker-старт с Postgres, миграциями и `collectstatic`;
- production-сервер на `gunicorn` + `UvicornWorker` с graceful reload.

## Демо-стенд

Production-стенд развернут на VPS `46.173.17.207`. Публичный домен —
`46-173-17-207.sslip.io` (через сервис sslip.io, который автоматически
резолвится в IP без регистрации DNS). Caddy выпускает Let's Encrypt
сертификат и проксирует HTTPS-трафик на Django.

- Главная: https://46-173-17-207.sslip.io/
- Админка: https://46-173-17-207.sslip.io/admin/
  Логин/пароль: `admin / admin12345` (создается миграцией
  [0002_create_default_admin_user.py](api/migrations/0002_create_default_admin_user.py)).
- Swagger UI: https://46-173-17-207.sslip.io/api/docs/
- Redoc: https://46-173-17-207.sslip.io/api/redoc/
- OpenAPI schema (JSON): https://46-173-17-207.sslip.io/api/schema/
- Health-check: https://46-173-17-207.sslip.io/health/

## API-документация

Проект использует чистые async Django views без DRF, поэтому полностью
автоматический schema-discovery в духе `drf-spectacular` недоступен. Вместо
этого в [api/openapi.py](api/openapi.py) живет программный генератор OpenAPI
3.1 спецификации:

- пути endpoint-ов резолвятся через `reverse()` — переименование URL
  автоматически отражается в схеме;
- спецификация собирается во время запроса на `/api/schema/`, а не как
  статический YAML;
- Swagger UI на `/api/docs/` и Redoc на `/api/redoc/` рендерят ту же схему,
  но фронтенд подгружается с CDN — никаких тяжелых JS-зависимостей в
  Python-проекте.

## Локальный запуск через Poetry

1. Скопировать `.env.example` в `.env`.
2. Установить зависимости:
   ```bash
   poetry install --no-root
   ```
3. Применить миграции:
   ```bash
   poetry run python manage.py migrate
   ```
4. Запустить приложение:
   ```bash
   poetry run uvicorn django5_stripe.asgi:application --reload
   ```
5. Открыть:
   - админку: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
   - healthcheck: [http://127.0.0.1:8000/health/](http://127.0.0.1:8000/health/)

После первого `migrate` в базе уже будут:
- демо-товары;
- два демо-заказа для `USD` и `EUR`;
- встроенный администратор `admin / admin12345`.

### Demo Stripe pricing (Coupon, Tax Rate)

Раньше demo-скидки и налог создавались внутри миграций `0005`/`0006`,
которые делали реальные сетевые вызовы в Stripe API при `migrate`. Это
анти-паттерн — миграции должны быть детерминированы и не зависеть от
внешней сети. Сейчас миграции `0005`/`0006` пустые (no-op, оставлены
только для совместимости истории), а seed Stripe pricing вынесен в
management-команду:

```bash
poetry run python manage.py seed_demo_pricing
```

Команда идемпотентна:
- если ключи Stripe не заданы — мягко завершается с предупреждением;
- если объекты уже существуют в Stripe — переиспользует их по
  `metadata.seed_source` и не создает дубликаты;
- сохраняет `stripe_coupon_id` и `stripe_tax_rate_id` в локальные модели
  `Discount` и `Tax` и привязывает demo-заказ `4002` к скидке и налогу.

После выполнения в админке появятся:
- `Demo 10% Off`;
- `Demo 5 EUR Off`;
- `Demo VAT 20%`.

## Локальный запуск через Docker

### Dev-режим

```bash
./run-docker.sh -d
```

Этот режим:
- использует `dev`-настройки Django;
- работает по обычному `http://`;
- монтирует проект как bind mount;
- автоматически применяет миграции;
- не делает `collectstatic` на каждом старте.

Открывать:
- [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
- [http://127.0.0.1:8000/health/](http://127.0.0.1:8000/health/)

Локальные команды `manage.py` автоматически подгружают корневой `.env`, поэтому
Stripe-ключи и остальные настройки не нужно каждый раз отдельно экспортировать
в shell перед `migrate`, `runserver` или `uvicorn`.

### Production-like режим

```bash
./run-docker.sh
```

Этот режим:
- использует `prod`-настройки Django;
- поднимает отдельный контейнер `Postgres`;
- автоматически выполняет `migrate` и `collectstatic` при старте;
- ближе к будущему реальному деплою, чем dev-compose.

Важно:
- `prod`-режим предполагает reverse proxy или ingress перед приложением,
  который завершает HTTPS и выставляет `X-Forwarded-Proto: https`;
- для этого режима используются отдельные переменные
  `DJANGO_ALLOWED_HOSTS_PROD`, `DJANGO_CSRF_TRUSTED_ORIGINS_PROD` и
  `DOMAIN_URL_PROD`, чтобы он не наследовал локальные HTTP-настройки dev.

## Ключи Stripe по валютам

Проект поддерживает два режима конфигурации:

1. Один Stripe account на обе валюты `USD` и `EUR`  
   Достаточно заполнить:
   - `STRIPE_SECRET_KEY`
   - `STRIPE_PUBLISHABLE_KEY`

2. Разные keypair по валютам  
   Дополнительно можно задать:
   - `STRIPE_USD_SECRET_KEY`
   - `STRIPE_USD_PUBLISHABLE_KEY`
   - `STRIPE_EUR_SECRET_KEY`
   - `STRIPE_EUR_PUBLISHABLE_KEY`

Если валютные ключи не заданы, приложение автоматически использует общий
keypair.

## База данных

Проект умеет работать в двух режимах:

- `SQLite` для локальной разработки и тестов;
- `Postgres` для production и production-like Docker-окружения.

Переключение идет так:
- если задан `DATABASE_URL`, используется он;
- иначе при `DJANGO_USE_POSTGRES=True` используется набор `POSTGRES_*`;
- иначе приложение остается на SQLite.

## Healthcheck

Маршрут [http://127.0.0.1:8000/health/](http://127.0.0.1:8000/health/) проверяет:
- что приложение отвечает;
- что основная база данных доступна.

Успешный ответ:

```json
{
  "status": "ok",
  "database": "ok"
}
```

Если БД недоступна, endpoint вернет `503`.

## Webhook

Для корректной фиксации успешных и неуспешных оплат нужен:
- `STRIPE_WEBHOOK_SECRET`

Локально webhook удобно тестировать через Stripe CLI:

```bash
stripe listen --forward-to http://127.0.0.1:8000/stripe/webhook/
```

Webhook endpoint:
- декорирован `@csrf_exempt` — Stripe не передает CSRF-токен и cookies,
  поэтому без декоратора `CsrfViewMiddleware` отвергал бы каждый POST с 403;
- проверяет подпись через `stripe.Webhook.construct_event(...)` —
  без валидной `Stripe-Signature` событие не обрабатывается;
- защищен от replay через журнал `ProcessedStripeEvent`: повторная доставка
  того же `event.id` молча игнорируется и не сдвигает повторно `paid_at`
  или статусы заказов.

## TLS/HTTPS через Caddy + Let's Encrypt

В `docker-compose.yml` есть отдельный сервис `caddy` ([caddy/Caddyfile](caddy/Caddyfile)),
который слушает 80/443, автоматически получает и обновляет Let's Encrypt
сертификат и проксирует на сервис `web` (Django+gunicorn) на 8000. Web-контейнер
больше не публикует порт наружу — только `127.0.0.1:8000` для healthcheck CD.

### Шаги

1. **Указать домен.** Let's Encrypt не выдаёт сертификаты на голый IP, нужен
   DNS-A-запись на сервер. Если своего домена нет, проще всего использовать
   `sslip.io`: домен вида `46-173-17-207.sslip.io` автоматически резолвится в
   IP `46.173.17.207` без регистрации. На сервере отредактируйте `.env`:

   ```env
   CADDY_DOMAIN=46-173-17-207.sslip.io
   DJANGO_ALLOWED_HOSTS_PROD=46-173-17-207.sslip.io
   DJANGO_CSRF_TRUSTED_ORIGINS_PROD=https://46-173-17-207.sslip.io
   DOMAIN_URL_PROD=https://46-173-17-207.sslip.io
   ```

2. **Открыть 80 и 443 на firewall** (bootstrap-скрипт уже это делает):

   ```bash
   ufw allow 80/tcp
   ufw allow 443/tcp
   ```

3. **Перезапустить compose:**

   ```bash
   cd /opt/django5_stripe
   docker compose -f docker-compose.yml up -d --build
   ```

   В логах `docker compose logs caddy` будет видно, как Caddy запрашивает и
   получает сертификат у Let's Encrypt (challenge ACME-HTTP-01).

4. **Проверить:**

   ```bash
   curl -I https://46-173-17-207.sslip.io/health/
   # HTTP/2 200
   # server: Caddy
   ```

   В браузере домен открывается с зелёным замочком, без warning.

### Когда появится свой домен

Просто заменить значение `CADDY_DOMAIN` в `.env`, обновить `DJANGO_ALLOWED_HOSTS_PROD`,
`DJANGO_CSRF_TRUSTED_ORIGINS_PROD`, `DOMAIN_URL_PROD` и сделать
`docker compose up -d` — Caddy автоматически выпустит новый сертификат на
новый домен. Старые сертификаты остаются в volume `caddy_data`.

### Stripe webhook на TLS-домене

После настройки HTTPS в Stripe Dashboard замените URL webhook'а на
`https://46-173-17-207.sslip.io/stripe/webhook/` — Stripe не принимает голые
HTTP в live mode, а в test mode тоже желательно использовать HTTPS, чтобы
поведение совпадало с production.

## CI

GitHub Actions workflow для PR-проверок:
- [.github/workflows/ci.yml](.github/workflows/ci.yml) — `manage.py check` + `python manage.py test`.

## CI/CD: автодеплой по push в `main`

Production-стенд: `46.173.17.207` (root).

Workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) при пуше
в `main` запускает два job-а:

1. **test** — повторяет проверки CI: `manage.py check` + `manage.py test`.
   Дублирование намеренное — defense in depth: даже если коммит попал в `main`
   мимо PR-проверок, прод не получит обновление без зеленых тестов.
2. **deploy** — подключается к серверу по SSH, делает `git fetch + reset
   --hard origin/main`, пересобирает docker compose stack и проверяет
   `/health/` до 30 раз с интервалом 2с. Если health-check не прошел — шаг
   падает, и в actions-логе видны последние 100 строк `docker compose logs`.

Параллельные деплои блокируются через `concurrency: deploy-production`.

### Первоначальная настройка сервера

Один раз вручную, по SSH:

```bash
ssh root@46.173.17.207

# Bootstrap — устанавливает Docker, ufw, клонирует репо, поднимает stack.
REPO_URL=https://github.com/<owner>/<repo>.git \
  bash <(curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/server-bootstrap.sh)

# После bootstrap отредактируйте production .env с реальными секретами:
nano /opt/django5_stripe/.env
docker compose -f /opt/django5_stripe/docker-compose.yml up -d
```

Скрипт [scripts/server-bootstrap.sh](scripts/server-bootstrap.sh) идемпотентен —
повторный запуск только обновит недостающие части.

### Доступ GitHub Actions к серверу по SSH

На сервере (один раз):

```bash
# Сгенерируйте отдельный deploy-ключ ТОЛЬКО для GitHub Actions.
ssh-keygen -t ed25519 -f ~/.ssh/github-deploy -N "" -C "github-actions deploy"

# Разрешите вход по этому ключу.
cat ~/.ssh/github-deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Распечатайте приватный ключ — его нужно сохранить в GitHub Secrets.
cat ~/.ssh/github-deploy
```

В `Settings → Secrets and variables → Actions → New repository secret`
заполните:

| Secret | Значение |
|---|---|
| `SSH_HOST` | `46.173.17.207` |
| `SSH_USER` | `root` |
| `SSH_PRIVATE_KEY` | Полное содержимое `~/.ssh/github-deploy` (включая `-----BEGIN OPENSSH PRIVATE KEY-----`). |
| `SSH_PORT` | (опционально) `22` по умолчанию. |
| `DEPLOY_PATH` | (опционально) `/opt/django5_stripe` по умолчанию. |

После этого каждый push в `main` будет автоматически выкатываться на
сервер. Ручной деплой запускается через `Actions → CD → Run workflow`.

### Production-секреты

Реальные значения `DJANGO_SECRET_KEY`, `STRIPE_*`, `POSTGRES_PASSWORD`
живут в `/opt/django5_stripe/.env` на сервере с правами `600`. Они
сознательно **не** пробрасываются через GitHub Actions, чтобы не утечь в
логи workflow. Меняются вручную: SSH → отредактировать `.env` →
`docker compose up -d`.
