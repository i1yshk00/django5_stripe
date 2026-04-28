"""Тесты вспомогательных функций пакета настроек."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from django5_stripe.settings.utils import load_project_dotenv


class LoadProjectDotenvTests(SimpleTestCase):
    """Проверки локальной загрузки `.env` без отдельной внешней зависимости."""

    def test_loader_reads_missing_values_and_keeps_existing_environment(self):
        """Загрузчик должен подхватывать недостающие ключи и не перетирать env.

        Это критично для проекта по двум причинам:
        - локальный `.env` должен автоматически подхватываться командами
          `manage.py`, чтобы миграции видели Stripe-ключи;
        - внешнее окружение Docker/CI должно иметь приоритет над значениями
          из файла, если переменная уже задана процессу.
        """
        with TemporaryDirectory() as temporary_directory:
            dotenv_path = Path(temporary_directory) / '.env'
            dotenv_path.write_text(
                '\n'.join(
                    [
                        '# Комментарий должен игнорироваться.',
                        'EXISTING_KEY=from_file',
                        'NEW_KEY="quoted value"',
                        'export EXPORTED_KEY=visible',
                    ]
                ),
                encoding='utf-8',
            )

            with patch.dict(
                os.environ,
                {
                    'EXISTING_KEY': 'from_environment',
                },
                clear=True,
            ):
                load_project_dotenv(dotenv_path)

                self.assertEqual(
                    os.environ['EXISTING_KEY'],
                    'from_environment',
                )
                self.assertEqual(os.environ['NEW_KEY'], 'quoted value')
                self.assertEqual(os.environ['EXPORTED_KEY'], 'visible')
