"""Модель налога, связанного с Tax Rate в Stripe."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from api.services.pricing import (
    create_stripe_tax_rate_for_tax,
    update_stripe_tax_rate_for_tax,
)


class Tax(models.Model):
    """Налоговая ставка, которую можно привязать к заказу.

    В модели хранится `stripe_tax_rate_id`, чтобы Stripe Checkout отображал
    налог в своем интерфейсе нативно, а не только как локально рассчитанную сумму.
    """

    name = models.CharField(max_length=255)
    stripe_tax_rate_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    inclusive = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Налог'
        verbose_name_plural = 'Налоги'

    def __str__(self) -> str:
        """Возвращает человекочитаемое имя налоговой ставки."""
        return self.name

    def clean(self) -> None:
        """Проверяет бизнес-ограничения локального налога и Stripe Tax Rate."""
        errors = {}

        if self.percentage > Decimal('100'):
            errors['percentage'] = 'Ставка налога не может быть больше 100%.'

        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()

            if previous is not None:
                if previous.stripe_tax_rate_id and previous.stripe_tax_rate_id != self.stripe_tax_rate_id:
                    errors['stripe_tax_rate_id'] = (
                        'Нельзя вручную менять Stripe Tax Rate ID у уже '
                        'синхронизированной налоговой записи. Создайте новую '
                        'запись или оставьте текущий идентификатор.'
                    )

                if previous.percentage != self.percentage:
                    errors['percentage'] = (
                        'После создания Stripe Tax Rate нельзя менять '
                        'процентную ставку. Создайте новую налоговую запись.'
                    )

                if previous.inclusive != self.inclusive:
                    errors['inclusive'] = (
                        'После создания Stripe Tax Rate нельзя менять режим '
                        'inclusive/exclusive. Создайте новую налоговую запись.'
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Сохраняет налог и при необходимости создает/синхронизирует Tax Rate.

        На создании локальной записи метод автоматически заводит удаленный
        Stripe Tax Rate и сохраняет его `id` в `stripe_tax_rate_id`.

        После этого разрешаем менять только те поля, которые Stripe позволяет
        синхронизировать у существующей ставки без пересоздания объекта:
        название и флаг `active`.
        """
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        self.full_clean()

        should_create_remote_tax_rate = not self.stripe_tax_rate_id
        should_update_remote_tax_rate = (
            previous is not None
            and bool(self.stripe_tax_rate_id)
            and (
                previous.name != self.name
                or previous.active != self.active
            )
        )

        if should_update_remote_tax_rate:
            update_stripe_tax_rate_for_tax(self)

        if should_create_remote_tax_rate:
            self.stripe_tax_rate_id = create_stripe_tax_rate_for_tax(self)

        return super().save(*args, **kwargs)
