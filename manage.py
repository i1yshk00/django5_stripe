#!/usr/bin/env python
"""Точка входа для запуска management-команд Django."""

import os
import sys


def main():
    """Запускает стандартный механизм обработки management-команд Django."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django5_stripe.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'Не удалось импортировать Django. Проверьте, что зависимости '
            'установлены и виртуальное окружение активировано.'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
