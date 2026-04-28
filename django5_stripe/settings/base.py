"""Базовые настройки Django, общие для dev и production-окружений.

Этот модуль отвечает за такие вещи, которые одинаково важны и в локальной
разработке, и в production:
- регистрация приложений и middleware;
- шаблоны;
- базовая конфигурация базы данных;
- static files;
- logging;
- стандартные настройки безопасности и локализации.

На production-ready этапе здесь дополнительно появляется:
- поддержка Postgres через env-конфигурацию;
- WhiteNoise для раздачи собранной статики;
- единая настройка логирования в stdout.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from .utils import env_bool, env_int


# Корень проекта, а не пакет django5_stripe.
BASE_DIR = Path(__file__).resolve().parents[2]


def _build_postgres_database_config_from_url(database_url: str) -> dict[str, object]:
    """Собирает Django-конфиг БД из `DATABASE_URL`.

    Такой формат удобен для большинства облачных платформ и managed Postgres,
    потому что они обычно отдают один готовый URL подключения.

    Args:
        database_url: Строка подключения формата
            `postgresql://user:password@host:port/dbname`.

    Returns:
        Словарь конфигурации Django для `django.db.backends.postgresql`.
    """
    parsed_url = urlparse(database_url)

    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed_url.path.lstrip('/')),
        'USER': unquote(parsed_url.username or ''),
        'PASSWORD': unquote(parsed_url.password or ''),
        'HOST': parsed_url.hostname or 'localhost',
        'PORT': str(parsed_url.port or 5432),
        'CONN_MAX_AGE': env_int('DJANGO_DB_CONN_MAX_AGE', 60),
        'CONN_HEALTH_CHECKS': True,
    }


def _build_postgres_database_config_from_env() -> dict[str, object]:
    """Собирает Django-конфиг Postgres из отдельных env-переменных.

    Этот вариант нужен прежде всего для Docker Compose, где удобно явно
    задавать имя сервиса БД, логин, пароль и имя базы отдельными переменными.
    """
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'django5_stripe'),
        'USER': os.getenv('POSTGRES_USER', 'django5_stripe'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'django5_stripe'),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': env_int('DJANGO_DB_CONN_MAX_AGE', 60),
        'CONN_HEALTH_CHECKS': True,
    }


def _build_default_database_config() -> dict[str, object]:
    """Выбирает подходящий backend базы данных для текущего окружения.

    Приоритет такой:
    1. если задан `DATABASE_URL`, используем его как самый явный источник;
    2. если включен флаг `DJANGO_USE_POSTGRES` или заданы переменные `POSTGRES_*`,
       собираем конфиг Postgres из отдельных env;
    3. иначе остаемся на SQLite, что удобно для локальной разработки и тестов.
    """
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        return _build_postgres_database_config_from_url(database_url)

    if env_bool('DJANGO_USE_POSTGRES', False) or os.getenv('POSTGRES_DB'):
        return _build_postgres_database_config_from_env()

    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }


# Секретный ключ Django.
# В локальной разработке допускается безопасный placeholder, но на деплое
# значение обязательно должно приходить из переменных окружения.
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-local-dev-only-change-me',
)


# Список приложений проекта.
# Unfold должен стоять перед `django.contrib.admin`, чтобы переопределить
# шаблоны и стили стандартной админки Django.
INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'api.apps.ApiConfig',
]

# Базовый набор middleware для сессий, аутентификации, CSRF-защиты
# и стандартной обработки запросов.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'django5_stripe.urls'

# Настройки шаблонов.
# Шаблоны вынесены в корневую директорию `templates`, а не хранятся внутри app,
# потому что мы заранее договорились складывать их в корень проекта по app.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'django5_stripe.wsgi.application'
ASGI_APPLICATION = 'django5_stripe.asgi.application'


# Конфигурация базы данных теперь умеет автоматически переключаться:
# - на SQLite для простой локальной разработки и тестов;
# - на Postgres для production и Docker-окружения.
DATABASES = {
    'default': _build_default_database_config()
}


# Стандартные валидаторы пароля Django.
# Они полезны и в dev, и в production, поскольку доступ к админке входит в ТЗ.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Базовые настройки локализации проекта.
# Так как проект делается для русскоязычной аудитории и комментарии мы ведем
# на русском, язык интерфейса тоже фиксируем как `ru`.
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True


# Статические файлы.
# `STATICFILES_DIRS` указывает на корневую директорию `static`, где мы храним
# ресурсы в раскладке по приложениям, например `static/api/js/...`.
# Публичный URL-префикс для статики.
# Используем каноническую форму с ведущим `/`, чтобы и шаблоны, и ASGI-обертка
# для локальной раздачи static работали предсказуемо.
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Базовый backend статики держим простым, чтобы локальный `runserver` не падал
# с "Missing staticfiles manifest entry" до первого `collectstatic`.
# Production-окружение переопределяет `staticfiles` на manifest-backend WhiteNoise
# в `prod.py` — так dev и prod не делят одно поведение поверх разных артефактов.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# WhiteNoise по умолчанию кэширует неизменяемые asset-файлы максимально долго.
# Это особенно полезно в production после `collectstatic`, где имена файлов
# уже содержат content-hash.
WHITENOISE_MAX_AGE = env_int('DJANGO_WHITENOISE_MAX_AGE', 31536000)


# Единая настройка логирования в stdout.
# Для контейнерного деплоя это самый практичный формат:
# логи сразу видны в `docker logs`, в системах оркестрации и на PaaS.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': (
                '%(asctime)s | %(levelname)s | %(name)s | '
                '%(message)s'
            ),
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'api': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}


# Явно фиксируем тип первичного ключа для новых моделей.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
