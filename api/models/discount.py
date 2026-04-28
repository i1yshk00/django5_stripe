"""Модель скидки, которая может быть привязана к заказу."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from api.services.pricing import (
    create_stripe_coupon_for_discount,
    update_stripe_coupon_for_discount,
)

from .item import Currency


class DiscountType(models.TextChoices):
    """Поддерживаемые типы скидок."""

    PERCENT = 'percent', 'Процентная скидка'
    FIXED = 'fixed', 'Фиксированная сумма'


class Discount(models.Model):
    """
    Скидка, связанная с объектом Coupon в Stripe.

    Мы храним `stripe_coupon_id`, чтобы при создании Checkout Session передать
    скидку в Stripe как ссылку на уже существующий coupon, а не вычислять ее
    только локально внутри проекта.
    """

    name = models.CharField(max_length=255)
    stripe_coupon_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        blank=True,
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Скидка'
        verbose_name_plural = 'Скидки'

    def __str__(self) -> str:
        """Возвращает название скидки для admin и отладочного вывода."""
        return self.name

    def clean(self) -> None:
        """
        Проверяет согласованность типа скидки, величины и валюты.

        Логика валидации зависит от `discount_type`:
        - процентная скидка должна быть в диапазоне 0..100 и не иметь валюты;
        - фиксированная скидка обязана иметь валюту.
        """
        errors = {}

        if self.currency:
            self.currency = self.currency.lower()

        if self.discount_type == DiscountType.PERCENT:
            if self.value > Decimal('100'):
                errors['value'] = 'Процент скидки не может быть больше 100.'
            if self.currency:
                errors['currency'] = (
                    'Для процентной скидки валюта не задается.'
                )

        if self.discount_type == DiscountType.FIXED and not self.currency:
            errors['currency'] = (
                'Для фиксированной скидки нужно указать валюту.'
            )

        if errors:
            raise ValidationError(errors)

        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()

            if previous is not None:
                immutable_changes = {}

                if previous.stripe_coupon_id and previous.stripe_coupon_id != self.stripe_coupon_id:
                    immutable_changes['stripe_coupon_id'] = (
                        'Нельзя вручную менять Stripe Coupon ID у уже '
                        'синхронизированной скидки. Создайте новую скидку или '
                        'оставьте текущий идентификатор без изменений.'
                    )

                if previous.discount_type != self.discount_type:
                    immutable_changes['discount_type'] = (
                        'После создания Stripe Coupon нельзя менять тип скидки. '
                        'Создайте новую скидку с нужными параметрами.'
                    )

                if previous.value != self.value:
                    immutable_changes['value'] = (
                        'После создания Stripe Coupon нельзя менять размер скидки. '
                        'Создайте новую скидку с нужным значением.'
                    )

                if previous.currency != self.currency:
                    immutable_changes['currency'] = (
                        'После создания Stripe Coupon нельзя менять валюту '
                        'фиксированной скидки. Создайте новую скидку.'
                    )

                if immutable_changes:
                    raise ValidationError(immutable_changes)

    def save(self, *args, **kwargs):
        """Сохраняет скидку и при необходимости создает/синхронизирует Coupon.

        Поведение метода:
        - если `stripe_coupon_id` еще не задан, сначала создается удаленный
          Stripe Coupon, затем его `id` сохраняется локально;
        - если Coupon уже существует, локально разрешаем обновлять только те
          поля, которые можно безопасно синхронизировать со Stripe;
        - неизменяемые поля Stripe Coupon защищены в `clean()`, чтобы локальная
          запись не расходилась с реальным удаленным объектом.
        """
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        self.full_clean()

        should_create_remote_coupon = not self.stripe_coupon_id
        should_update_remote_coupon = (
            previous is not None
            and bool(self.stripe_coupon_id)
            and previous.name != self.name
        )

        if should_update_remote_coupon:
            update_stripe_coupon_for_discount(self)

        if should_create_remote_coupon:
            self.stripe_coupon_id = create_stripe_coupon_for_discount(self)

        return super().save(*args, **kwargs)
