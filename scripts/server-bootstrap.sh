#!/usr/bin/env bash
#
# Первоначальная настройка production-хоста под автодеплой django5_stripe.
#
# Запускается ОДИН РАЗ вручную на сервере (например, на 46.173.17.207):
#
#     ssh root@46.173.17.207
#     curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/server-bootstrap.sh \
#       | REPO_URL=https://github.com/<owner>/<repo>.git bash
#
# Скрипт идемпотентен: повторный запуск не сломает существующую установку,
# а только обновит недостающие части.
#
# После выполнения сервер готов к автодеплоям: GitHub Actions подключится по
# SSH, сделает `git pull` и пересоберет docker compose stack.

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# Параметры — переопределяются переменными окружения перед запуском.
# ──────────────────────────────────────────────────────────────────────────

DEPLOY_PATH="${DEPLOY_PATH:-/opt/django5_stripe}"
REPO_URL="${REPO_URL:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

# REPO_URL обязателен, только если в DEPLOY_PATH ещё нет git-клона. Если
# скрипт запущен из уже существующего клона (например, `cd /opt/django5_stripe
# && bash scripts/server-bootstrap.sh`), URL автоматически берётся из
# `git remote get-url origin` — не нужно дублировать его в env.
if [[ -z "$REPO_URL" && -d "$DEPLOY_PATH/.git" ]]; then
    REPO_URL="$(git -C "$DEPLOY_PATH" remote get-url origin 2>/dev/null || true)"
fi

if [[ -z "$REPO_URL" ]]; then
    echo "ERROR: переменная REPO_URL не задана и в $DEPLOY_PATH нет git-клона."
    echo "Пример запуска:"
    echo "  REPO_URL=https://github.com/<owner>/<repo>.git bash server-bootstrap.sh"
    exit 1
fi

echo "==> Bootstrap django5_stripe on $(hostname)"
echo "    DEPLOY_PATH=$DEPLOY_PATH"
echo "    REPO_URL=$REPO_URL"
echo "    DEPLOY_BRANCH=$DEPLOY_BRANCH"
echo

# ──────────────────────────────────────────────────────────────────────────
# 1. Базовые системные пакеты.
# ──────────────────────────────────────────────────────────────────────────

echo "==> Installing base packages (curl, git, ufw, ca-certificates)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg ufw >/dev/null

# ──────────────────────────────────────────────────────────────────────────
# 2. Docker Engine + Compose plugin (через официальный репозиторий Docker).
# ──────────────────────────────────────────────────────────────────────────

if ! command -v docker >/dev/null 2>&1; then
    echo "==> Installing Docker Engine"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    . /etc/os-release
    DISTRO="${ID:-debian}"
    CODENAME="${VERSION_CODENAME:-bookworm}"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/$DISTRO $CODENAME stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin >/dev/null

    systemctl enable --now docker
else
    echo "==> Docker уже установлен — пропускаем"
fi

# ──────────────────────────────────────────────────────────────────────────
# 3. Firewall: открываем только 22, 80, 443 наружу.
# ──────────────────────────────────────────────────────────────────────────

echo "==> Configuring UFW firewall"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'SSH' >/dev/null
ufw allow 80/tcp comment 'HTTP' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw --force enable >/dev/null

# ──────────────────────────────────────────────────────────────────────────
# 4. Клонируем репозиторий или обновляем существующий клон.
# ──────────────────────────────────────────────────────────────────────────

mkdir -p "$DEPLOY_PATH"
if [[ ! -d "$DEPLOY_PATH/.git" ]]; then
    echo "==> Cloning $REPO_URL into $DEPLOY_PATH"
    git clone --branch "$DEPLOY_BRANCH" "$REPO_URL" "$DEPLOY_PATH"
else
    echo "==> Repo already exists, fetching latest"
    git -C "$DEPLOY_PATH" fetch --all --prune
    git -C "$DEPLOY_PATH" reset --hard "origin/$DEPLOY_BRANCH"
fi

# ──────────────────────────────────────────────────────────────────────────
# 5. Создаем `.env`-плейсхолдер, если его еще нет.
#
# Реальные значения секретов нужно проставить руками после bootstrap. Они
# намеренно не пробрасываются через GitHub Actions, чтобы не утекли в логи.
# ──────────────────────────────────────────────────────────────────────────

ENV_FILE="$DEPLOY_PATH/.env"
ENV_HAD_PLACEHOLDERS=0

if [[ ! -f "$ENV_FILE" ]]; then
    echo "==> Creating placeholder .env at $ENV_FILE"
    cat >"$ENV_FILE" <<'ENV_EOF'
# Production env file — заполните реальными значениями перед первым деплоем.
DJANGO_ENV=prod
DJANGO_SECRET_KEY=PLEASE_CHANGE_TO_LONG_RANDOM_STRING
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS_PROD=your-domain.example,46.173.17.207
DJANGO_CSRF_TRUSTED_ORIGINS_PROD=https://your-domain.example
DOMAIN_URL_PROD=https://your-domain.example

POSTGRES_DB=django5_stripe
POSTGRES_USER=django5_stripe
POSTGRES_PASSWORD=PLEASE_CHANGE_TO_STRONG_PASSWORD

STRIPE_SECRET_KEY=sk_live_or_test_REAL_KEY
STRIPE_PUBLISHABLE_KEY=pk_live_or_test_REAL_KEY
STRIPE_WEBHOOK_SECRET=whsec_REAL_WEBHOOK_SIGNING_SECRET
STRIPE_API_VERSION=2026-02-25.clover
ENV_EOF
    chmod 600 "$ENV_FILE"
    ENV_HAD_PLACEHOLDERS=1
    echo "    -> $ENV_FILE создан с PLACEHOLDER-значениями"
else
    echo "==> .env уже существует, оставляем как есть"
fi

# ──────────────────────────────────────────────────────────────────────────
# 6. Поднимаем сервис только если в .env реальные секреты.
#
# Если .env только что создан с PLACEHOLDER-значениями, docker compose НЕ
# запускается автоматически. Иначе Postgres инициализирует volume с
# placeholder-паролем, и после правки .env пароль не совпадет — придется
# вручную пересоздавать volume. Чтобы избежать этой ловушки, оставляем
# финальный `up -d` пользователю — после ручной правки .env.
# ──────────────────────────────────────────────────────────────────────────

if [[ "$ENV_HAD_PLACEHOLDERS" -eq 1 ]]; then
    echo
    echo "==> Bootstrap почти готов, но docker compose НЕ запущен."
    echo "    Причина: .env только что создан с PLACEHOLDER-значениями."
    echo "    Если запустить compose сейчас, Postgres зафиксирует"
    echo "    placeholder-пароль внутри volume, и после правки .env"
    echo "    придется пересоздавать том вручную (docker volume rm ...)."
    echo
    echo "Дальнейшие шаги:"
    echo "  1. Отредактируйте $ENV_FILE и проставьте реальные секреты:"
    echo "       nano $ENV_FILE"
    echo "  2. Запустите stack:"
    echo "       cd $DEPLOY_PATH && docker compose -f docker-compose.yml up -d --build"
    echo "  3. В GitHub repository → Settings → Secrets установите:"
    echo "       SSH_HOST=46.173.17.207"
    echo "       SSH_USER=root"
    echo "       SSH_PRIVATE_KEY=<содержимое ~/.ssh/github-deploy>"
    echo "  4. Push в main — workflow CD автоматически выкатит обновление."
else
    echo "==> Building and starting docker compose stack"
    cd "$DEPLOY_PATH"
    docker compose -f docker-compose.yml up -d --build --remove-orphans

    echo
    echo "==> Bootstrap complete."
    echo "Если еще не настроены GitHub Secrets — добавьте:"
    echo "  SSH_HOST=46.173.17.207, SSH_USER=root, SSH_PRIVATE_KEY=..."
fi
