"""WSGI-конфигурация проекта для совместимости с классическими WSGI-серверами."""

import os

from django.core.wsgi import get_wsgi_application

# Оставляем тот же пакет настроек, что и для ASGI, чтобы dev/prod-логика
# была едина независимо от способа запуска приложения.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django5_stripe.settings')

application = get_wsgi_application()
