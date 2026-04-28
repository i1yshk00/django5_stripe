"""Вспомогательные функции для чтения переменных окружения.

В проекте мы сознательно не тянем отдельную зависимость только ради чтения
`.env`, поэтому базовый разбор env-файла реализован здесь. Этого достаточно
для локальной разработки и миграций, где важно автоматически подхватывать
Stripe-ключи и остальные параметры без ручного `export`.
"""

import os
from pathlib import Path


def _normalize_env_value(raw_value: str) -> str:
    """Нормализует значение переменной из `.env`.

    Функция делает только безопасный минимум:
    - убирает внешние пробелы;
    - снимает парные одинарные или двойные кавычки;
    - не пытается интерпретировать escape-последовательности.

    Такой консервативный разбор предсказуем и хорошо подходит для текущего
    проекта, где значения переменных — это в основном URL, ключи и флаги.
    """
    value = raw_value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]

    return value


def load_project_dotenv(dotenv_path: Path | None = None) -> None:
    """Подгружает `.env` в `os.environ`, не перетирая уже заданные переменные.

    Почему это важно:
    - `docker compose` и CI обычно прокидывают env сами;
    - локальный запуск через `poetry run python manage.py ...` часто ожидает,
      что настройки возьмутся из файла `.env` автоматически;
    - миграции с реальным Stripe API должны видеть ключи из `.env` без ручной
      подготовки окружения перед каждым запуском.

    Args:
        dotenv_path: Явный путь до env-файла. Если не передан, используется
            корневой `.env` проекта.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parents[2] / '.env'

    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()

        if not line or line.startswith('#'):
            continue

        if line.startswith('export '):
            line = line[len('export '):].strip()

        if '=' not in line:
            continue

        key, raw_value = line.split('=', 1)
        key = key.strip()

        if not key or key in os.environ:
            continue

        os.environ[key] = _normalize_env_value(raw_value)


def env_bool(name: str, default: bool = False) -> bool:
    """Читает переменную окружения и интерпретирует ее как логическое значение."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Читает строку из env и разбивает ее на список по запятым."""
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name: str, default: int = 0) -> int:
    """Читает переменную окружения и преобразует ее к целому числу."""
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)
