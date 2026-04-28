"""Настройки для production-окружения.

Здесь собраны параметры, которые делают приложение готовым к безопасному
деплою: отключение debug, HTTPS-only cookies, HSTS и учет reverse proxy.

Важно: базовые security-настройки в этом файле зафиксированы кодом. Это
уменьшает количество env-переменных и делает production-конфигурацию более
явной и читаемой.
"""

from .base import *
from .utils import env_list


# В production режим отладки фиксируем кодом как выключенный.
#
# Здесь не должно быть зависимости от `.env`, иначе production-like запуск
# может случайно унаследовать локальное `DJANGO_DEBUG=True` и перестать быть
# реально production-подобным.
DEBUG = False

# Список доменов и хостов, с которых приложение доступно снаружи.
# В production должен быть задан явно через переменные окружения.
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS')

# Список доверенных origin для CSRF-проверки.
# Обычно сюда попадает боевой HTTPS-домен приложения.
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

# Принудительный редирект с HTTP на HTTPS.
# Для production это стандартная базовая защита.
SECURE_SSL_REDIRECT = True

# Разрешает браузеру отправлять session-cookie только по HTTPS.
# Это защищает пользовательскую сессию в продакшене.
SESSION_COOKIE_SECURE = True

# Разрешает браузеру отправлять CSRF-cookie только по HTTPS.
# Это дополняет защиту форм и state-changing запросов.
CSRF_COOKIE_SECURE = True

# Время действия HSTS в секундах.
# Пока правило активно, браузер автоматически использует HTTPS для домена.
SECURE_HSTS_SECONDS = 31536000

# Распространять ли HSTS на поддомены.
# Имеет смысл, если вся зона обслуживается только по HTTPS.
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Разрешает заявлять домен для HSTS preload-списков браузеров.
# Включать стоит только если домен стабильно обслуживается по HTTPS.
SECURE_HSTS_PRELOAD = True

# Доверять ли заголовку X-Forwarded-Proto от балансировщика или reverse proxy.
# Обычно нужно при деплое за Nginx, Traefik, Render, Fly.io и подобными прокси.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# В production WhiteNoise должен работать в manifest-режиме и отдавать только
# заранее собранную статику из `STATIC_ROOT`. Это делает деплой предсказуемым и
# исключает зависимость от source tree при runtime-запуске контейнера.
WHITENOISE_AUTOREFRESH = False
WHITENOISE_USE_FINDERS = False

# В production переопределяем backend статики на manifest-режим:
# - имена файлов содержат content-hash;
# - WhiteNoise умеет gzip/brotli-сжатие и долгий cache-control.
# В base.py остается обычный backend, чтобы dev `runserver` не требовал
# `collectstatic` перед каждым запуском.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
