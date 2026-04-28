"""Конфигурация Django-приложения `api`."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Базовая конфигурация приложения с доменной логикой Stripe-проекта."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'Платежное API'
