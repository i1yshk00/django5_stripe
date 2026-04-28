"""Настройки для локальной разработки.

Этот модуль делает поведение проекта удобным для разработки:
- включает debug-режим;
- разрешает локальные хосты;
- не заставляет использовать HTTPS и HSTS.

Важно: security-настройки в этом файле зафиксированы кодом, а не приходят из
переменных окружения. Это упрощает конфигурацию локальной разработки и делает
поведение dev-окружения предсказуемым.
"""

from .base import *
from .utils import env_bool, env_list


# В dev-окружении оставляем режим отладки включенным по умолчанию,
# чтобы видеть traceback, debug pages и быстрее разбираться с ошибками.
DEBUG = env_bool('DJANGO_DEBUG', True)

# Список хостов, с которых Django принимает запросы.
# В локальной разработке сюда входят localhost и loopback-адреса.
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0')

# Источники, которым разрешено проходить CSRF-проверку.
# Нужны для форм и AJAX-запросов с локальных адресов приложения.
CSRF_TRUSTED_ORIGINS = env_list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'http://localhost:8000,http://127.0.0.1:8000',
)

# Перенаправлять ли все HTTP-запросы на HTTPS.
# В dev обычно выключено, потому что локально мы чаще работаем по http.
SECURE_SSL_REDIRECT = False

# Помечать ли session-cookie как доступную только по HTTPS.
# В локальной разработке выключено, иначе с http могут возникать проблемы.
SESSION_COOKIE_SECURE = False

# Помечать ли CSRF-cookie как доступную только по HTTPS.
# В dev тоже обычно выключено по той же причине, что и session-cookie.
CSRF_COOKIE_SECURE = False

# Сколько секунд браузер должен помнить, что сайт доступен только по HTTPS.
# Для dev значение обнуляем, чтобы HSTS не мешал локальной отладке.
SECURE_HSTS_SECONDS = 0

# Применять ли HSTS также к поддоменам.
# В dev выключено, потому что поддомены локально нам не нужны.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False

# Разрешать ли включение домена в preload-список HSTS браузеров.
# В dev это не используется.
SECURE_HSTS_PRELOAD = False

# Нужно ли доверять заголовку X-Forwarded-Proto от reverse proxy.
# Для локальной разработки это не нужно, поэтому настройка отключена явно.
SECURE_PROXY_SSL_HEADER = None

# В dev полезно разрешить WhiteNoise читать файлы напрямую из finder-ов и не
# требовать предварительно собранный manifest, чтобы изменения в static-ресурсах
# были сразу видны без production-сборки.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True

# В dev и test-режиме manifest-хранилище неудобно: оно ожидает заранее
# собранный `staticfiles.json` и падает на рендере шаблонов, если `collectstatic`
# еще не запускался. Поэтому для локальной работы и тестов используем обычное
# staticfiles-хранилище без обязательной production-сборки.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
