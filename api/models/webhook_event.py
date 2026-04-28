"""Журнал обработанных Stripe webhook-событий для защиты от replay.

Stripe гарантирует at-least-once доставку webhook-событий. Без журнала
повторный приход того же `event.id` повторно проиграет обработку и может,
например, дважды передвинуть `paid_at` или сменить статус заказа.

Решение — сохранить идентификатор события в БД с уникальным индексом и до
обработки делать `get_or_create`. Если запись уже была — игнорируем повтор.
"""

from __future__ import annotations

from django.db import models


class ProcessedStripeEvent(models.Model):
    """Подтверждение, что Stripe-событие уже обработано приложением."""

    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=128, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-processed_at',)
        verbose_name = 'Обработанное Stripe-событие'
        verbose_name_plural = 'Обработанные Stripe-события'

    def __str__(self) -> str:
        """Возвращает читаемое представление для admin и логов."""
        return f'{self.event_type or "stripe.event"} ({self.event_id})'
