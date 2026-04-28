"""ASGI-конфигурация проекта для запуска через Uvicorn и другие ASGI-серверы.

В обычном Django `runserver` раздача статики в debug-режиме происходит
автоматически. Но при запуске через чистый ASGI-сервер, такой как Uvicorn,
этого поведения по умолчанию уже нет: приложение обрабатывает только Django
маршруты, а запросы к `/static/...` начинают возвращать `404 Not Found`.

Для локальной разработки это неудобно, особенно когда админка зависит от
большого числа CSS и JS файлов. Поэтому в `DEBUG=True` мы оборачиваем Django
ASGI-приложение в `ASGIStaticFilesHandler`, чтобы dev-окружение работало так же
удобно, как и встроенный `runserver`.
"""

import os

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

# По умолчанию проект использует пакет настроек django5_stripe.settings,
# который сам выбирает dev/prod-конфигурацию по переменной окружения DJANGO_ENV.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django5_stripe.settings')

# Базовое ASGI-приложение Django.
django_asgi_application = get_asgi_application()

# В dev-режиме явно включаем раздачу статики самим Django. Это нужно именно для
# локального запуска через Uvicorn, где нет отдельного reverse proxy или CDN.
if settings.DEBUG:
    application = ASGIStaticFilesHandler(django_asgi_application)
else:
    application = django_asgi_application
