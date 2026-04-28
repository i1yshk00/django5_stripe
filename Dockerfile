# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=prod \
    POETRY_VERSION=1.8.4 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . .
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

# Entry point запускаем через shell-интерпретатор, а не прямым exec файла.
#
# Причина практическая: в dev-режиме проект монтируется в контейнер как bind
# mount, и права исходного файла на хосте могут не содержать executable-бит.
# Если вызывать `/app/docker/entrypoint.sh` напрямую, контейнер падает с
# `Permission denied`. Вызов через `/bin/sh` делает запуск устойчивым и для
# образа, и для локального bind-mounted кода.
ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
# Production CMD: gunicorn управляет пулом UvicornWorker'ов. Это дает
# несколько процессов, graceful reload, периодический `--max-requests`
# refresh и устойчивость к утечкам памяти в отдельном воркере. Чистый
# `uvicorn` без supervisor — single process без worker management,
# что не подходит для production-нагрузки.
# Dev-режим переопределяет `command` в docker-compose.dev.yml на простой
# `uvicorn --reload`, чтобы получать hot reload при bind-mount.
CMD ["gunicorn", "django5_stripe.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
