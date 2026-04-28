"""Модель товара, который можно оплатить через Stripe."""

from decimal import Decimal, ROUND_HALF_UP

from django.core.validators import MinValueValidator
from django.db import models


class Currency(models.TextChoices):
    """Поддерживаемые валюты проекта.

    В рамках текущего тестового задания мы заранее ограничиваемся USD и EUR,
    потому что именно эти валюты планируем использовать в демонстрации.
    """

    USD = 'usd', 'USD'
    EUR = 'eur', 'EUR'


class Item(models.Model):
    """Товар, доступный для прямой покупки через Stripe Checkout.

    Поля модели повторяют обязательную часть ТЗ:
    - `name`;
    - `description`;
    - `price`.

    Поле `currency` добавлено как бонусное расширение, чтобы заранее строить
    full-featured версию проекта без последующей миграции схемы.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self) -> str:
        """Возвращает компактное строковое представление товара для admin и shell."""
        return f'{self.name} ({self.currency.upper()})'

    @property
    def amount_minor_units(self) -> int:
        """Возвращает цену товара в minor units для передачи в Stripe.

        Stripe ожидает сумму не в долларах/евро с плавающей точкой, а в целых
        minor units: центах, евроцентах и т.д. Поэтому `12.34 USD` превращается
        в `1234`.
        """
        amount = (self.price * Decimal('100')).quantize(
            Decimal('1'),
            rounding=ROUND_HALF_UP,
        )
        return int(amount)

    def clean(self) -> None:
        """Нормализует валюту перед валидацией и сохранением."""
        if self.currency:
            self.currency = self.currency.lower()

    def save(self, *args, **kwargs):
        """Сохраняет модель только после полной валидации полей."""
        self.full_clean()
        return super().save(*args, **kwargs)
