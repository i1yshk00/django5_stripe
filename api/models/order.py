"""Модели заказа и его позиций для расширенной версии проекта."""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from .discount import DiscountType
from .item import Currency


# Денежные суммы в проекте нормализуем до двух знаков после запятой,
# потому что текущий scope ограничен валютами USD и EUR.
TWOPLACES = Decimal('0.01')


class CheckoutMode(models.TextChoices):
    """Поддерживаемые способы оплаты заказа в Stripe."""

    CHECKOUT_SESSION = 'checkout_session', 'Stripe Checkout Session'
    PAYMENT_INTENT = 'payment_intent', 'Stripe Payment Intent'


class PaymentStatus(models.TextChoices):
    """Упрощенное внутреннее состояние оплаты заказа."""

    DRAFT = 'draft', 'Черновик'
    PENDING = 'pending', 'Ожидает оплаты'
    PROCESSING = 'processing', 'В обработке'
    PAID = 'paid', 'Оплачен'
    FAILED = 'failed', 'Ошибка оплаты'
    CANCELED = 'canceled', 'Отменен'
    EXPIRED = 'expired', 'Истек'


class Order(models.Model):
    """Заказ, объединяющий одну или несколько товарных позиций.

    Модель спроектирована сразу под full-featured версию проекта:
    - умеет хранить скидку и налог;
    - умеет работать и с Checkout Session, и с Payment Intent;
    - хранит Stripe-идентификаторы для последующей синхронизации по webhook.
    """

    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
    )
    items = models.ManyToManyField(
        'api.Item',
        through='api.OrderItem',
        related_name='orders',
    )
    discount = models.ForeignKey(
        'api.Discount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    tax = models.ForeignKey(
        'api.Tax',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    checkout_mode = models.CharField(
        max_length=32,
        choices=CheckoutMode.choices,
        default=CheckoutMode.CHECKOUT_SESSION,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.DRAFT,
    )
    stripe_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_client_secret = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at', 'id')
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self) -> str:
        """Возвращает удобное имя заказа для админки и журналов."""
        if self.pk:
            return f'Заказ #{self.pk}'
        return 'Новый заказ'

    @staticmethod
    def quantize_amount(value: Decimal) -> Decimal:
        """Нормализует денежное значение к двум знакам после запятой."""
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    @property
    def subtotal_amount(self) -> Decimal:
        """Считает сумму всех позиций заказа до скидок и налогов."""
        subtotal = sum(
            (order_item.line_subtotal for order_item in self.order_items.all()),
            start=Decimal('0.00'),
        )
        return self.quantize_amount(subtotal)

    @property
    def discount_amount(self) -> Decimal:
        """Возвращает абсолютную сумму скидки для текущего заказа."""
        if not self.discount:
            return Decimal('0.00')

        subtotal = self.subtotal_amount
        if self.discount.discount_type == DiscountType.PERCENT:
            amount = subtotal * (self.discount.value / Decimal('100'))
            return self.quantize_amount(amount)

        return min(subtotal, self.quantize_amount(self.discount.value))

    @property
    def taxable_amount(self) -> Decimal:
        """Возвращает базу для расчета налога после применения скидки."""
        taxable_amount = self.subtotal_amount - self.discount_amount
        if taxable_amount < Decimal('0.00'):
            return Decimal('0.00')
        return self.quantize_amount(taxable_amount)

    @property
    def tax_amount(self) -> Decimal:
        """Возвращает сумму налога с учетом режима inclusive/exclusive."""
        if not self.tax:
            return Decimal('0.00')

        taxable_amount = self.taxable_amount
        if self.tax.inclusive:
            amount = taxable_amount * self.tax.percentage / (
                Decimal('100') + self.tax.percentage
            )
            return self.quantize_amount(amount)

        amount = taxable_amount * (self.tax.percentage / Decimal('100'))
        return self.quantize_amount(amount)

    @property
    def total_amount(self) -> Decimal:
        """Возвращает итоговую сумму заказа после скидок и налогов."""
        taxable_amount = self.taxable_amount
        if not self.tax or self.tax.inclusive:
            return taxable_amount
        return self.quantize_amount(taxable_amount + self.tax_amount)

    def clean(self) -> None:
        """Проверяет согласованность валюты заказа, скидки и позиций.

        Ограничение "один заказ — одна валюта" упрощает интеграцию со Stripe,
        потому что в одном checkout-потоке мы не должны смешивать line items
        в разных валютах.
        """
        errors = {}

        if self.currency:
            self.currency = self.currency.lower()

        if (
            self.discount
            and self.discount.discount_type == DiscountType.FIXED
            and self.discount.currency != self.currency
        ):
            errors['discount'] = (
                'Валюта фиксированной скидки должна совпадать с валютой заказа.'
            )

        if self.pk:
            invalid_items = self.order_items.exclude(currency=self.currency)
            if invalid_items.exists():
                errors['currency'] = (
                    'Все позиции заказа должны быть в одной валюте с заказом.'
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Сохраняет заказ только после полной бизнес-валидации."""
        self.full_clean()
        return super().save(*args, **kwargs)


class OrderItem(models.Model):
    """Позиция заказа с денежным снимком товара на момент добавления.

    Снапшоты имени, описания, цены и валюты защищают историю заказа от
    изменений в карточке товара после того, как заказ уже был сформирован.
    """

    order = models.ForeignKey(
        'api.Order',
        on_delete=models.CASCADE,
        related_name='order_items',
    )
    item = models.ForeignKey(
        'api.Item',
        on_delete=models.PROTECT,
        related_name='order_items',
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    item_name = models.CharField(max_length=255, blank=True)
    item_description = models.TextField(blank=True)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'
        constraints = [
            models.UniqueConstraint(
                fields=('order', 'item'),
                name='unique_item_per_order',
            ),
        ]

    def __str__(self) -> str:
        """Возвращает короткое представление позиции заказа."""
        return f'{self.item_name or self.item.name} x {self.quantity}'

    @property
    def line_subtotal(self) -> Decimal:
        """Считает стоимость позиции как `цена * количество`."""
        if self.unit_price is None:
            return Decimal('0.00')
        subtotal = self.unit_price * self.quantity
        return Order.quantize_amount(subtotal)

    def apply_item_snapshot(self) -> None:
        """Заполняет snapshot-поля данными товара, если они еще не записаны."""
        if not self.item_id:
            return

        if not self.item_name:
            self.item_name = self.item.name
        if not self.item_description:
            self.item_description = self.item.description
        if self.unit_price is None:
            self.unit_price = self.item.price
        if not self.currency:
            self.currency = self.item.currency

    def clean(self) -> None:
        """Проверяет, что позиция совместима с заказом по валюте и составу."""
        self.apply_item_snapshot()
        errors = {}

        if self.currency:
            self.currency = self.currency.lower()

        if self.unit_price is None:
            errors['unit_price'] = 'Нужно указать цену позиции заказа.'

        if self.order_id and self.currency != self.order.currency:
            errors['currency'] = (
                'Валюта позиции заказа должна совпадать с валютой заказа.'
            )

        if self.order_id and self.item_id and self.item.currency != self.order.currency:
            errors['item'] = (
                'Нельзя добавить в заказ товар в другой валюте.'
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Перед сохранением обновляет снимок товара и запускает валидацию."""
        self.apply_item_snapshot()
        self.full_clean()
        return super().save(*args, **kwargs)
