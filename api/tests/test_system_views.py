"""Тесты системных endpoint-ов проекта."""

from unittest.mock import patch

from django.db.utils import OperationalError
from django.test import TestCase
from django.urls import reverse


class HealthCheckViewTests(TestCase):
    """Проверки healthcheck endpoint-а."""

    def test_health_check_returns_ok_when_database_is_available(self):
        """При доступной БД endpoint должен отвечать кодом 200 и статусом ok."""
        response = self.client.get(reverse('api:health-check'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'status': 'ok',
                'database': 'ok',
            },
        )

    @patch('api.views.system._probe_default_database')
    def test_health_check_returns_503_when_database_is_unavailable(self, mocked_probe):
        """При недоступной БД endpoint должен явно сигнализировать о проблеме."""
        mocked_probe.side_effect = OperationalError('database is unavailable')

        response = self.client.get(reverse('api:health-check'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(response.json()['database'], 'unavailable')
