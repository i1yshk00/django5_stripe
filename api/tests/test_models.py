"""Тесты доменных моделей приложения `api`."""

from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from api.models import Discount, DiscountType, Item, Order, OrderItem, Tax


class ItemModelTests(TestCase):
    """Проверки модели Item."""

    def test_amount_minor_units_for_two_decimal_currency(self):
        """Цена товара должна корректно переводиться в minor units для Stripe."""
        item = Item.objects.create(
            name='Test item',
            description='Test description',
            price=Decimal('12.34'),
            currency='usd',
        )

        self.assertEqual(item.amount_minor_units, 1234)


class DiscountModelTests(TestCase):
    """Проверки правил валидации скидок."""

    @patch('api.models.discount.create_stripe_coupon_for_discount')
    def test_discount_creates_stripe_coupon_automatically(self, mocked_create_coupon):
        """При пустом `stripe_coupon_id` модель должна создать Coupon в Stripe."""
        mocked_create_coupon.return_value = 'coupon_auto_created'

        discount = Discount.objects.create(
            name='Auto coupon',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
        )

        self.assertEqual(discount.stripe_coupon_id, 'coupon_auto_created')
        mocked_create_coupon.assert_called_once()

    def test_fixed_discount_requires_currency(self):
        """Фиксированная скидка без валюты не должна сохраняться."""
        discount = Discount(
            name='Fixed discount',
            stripe_coupon_id='coupon_fixed',
            discount_type=DiscountType.FIXED,
            value=Decimal('10.00'),
        )

        with self.assertRaises(ValidationError):
            discount.full_clean()

    @patch('api.models.discount.create_stripe_coupon_for_discount')
    def test_discount_rejects_immutable_changes_after_remote_coupon_creation(self, mocked_create_coupon):
        """Нельзя менять value у скидки после создания Stripe Coupon."""
        mocked_create_coupon.return_value = 'coupon_locked'

        discount = Discount.objects.create(
            name='Locked coupon',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        discount.value = Decimal('15.00')

        with self.assertRaises(ValidationError):
            discount.save()

    def test_percent_discount_must_not_have_currency(self):
        """Процентная скидка не должна одновременно хранить валюту."""
        discount = Discount(
            name='Percent discount',
            stripe_coupon_id='coupon_percent',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
            currency='usd',
        )

        with self.assertRaises(ValidationError):
            discount.full_clean()


class OrderModelTests(TestCase):
    """Проверки расчета сумм и валютных ограничений заказа."""

    def test_order_item_snapshots_item_fields(self):
        """Позиция заказа должна сохранять снимок данных товара."""
        item = Item.objects.create(
            name='Laptop',
            description='14-inch laptop',
            price=Decimal('999.99'),
            currency='usd',
        )
        order = Order.objects.create(currency='usd')

        order_item = OrderItem.objects.create(order=order, item=item, quantity=2)

        self.assertEqual(order_item.item_name, 'Laptop')
        self.assertEqual(order_item.item_description, '14-inch laptop')
        self.assertEqual(order_item.unit_price, Decimal('999.99'))
        self.assertEqual(order_item.currency, 'usd')
        self.assertEqual(order_item.line_subtotal, Decimal('1999.98'))

    def test_order_item_rejects_mixed_currency(self):
        """Заказ не должен принимать товары в валюте, отличной от своей."""
        item = Item.objects.create(
            name='EUR item',
            description='Priced in EUR',
            price=Decimal('10.00'),
            currency='eur',
        )
        order = Order.objects.create(currency='usd')

        with self.assertRaises(ValidationError):
            OrderItem.objects.create(order=order, item=item, quantity=1)

    def test_order_calculates_discount_and_exclusive_tax(self):
        """Заказ должен корректно считать скидку, налог и итоговую сумму."""
        item = Item.objects.create(
            name='Book',
            description='Hardcover book',
            price=Decimal('10.00'),
            currency='usd',
        )
        discount = Discount.objects.create(
            name='Ten percent off',
            stripe_coupon_id='coupon_10_off',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        tax = Tax.objects.create(
            name='VAT 20%',
            stripe_tax_rate_id='txr_20',
            percentage=Decimal('20.00'),
            inclusive=False,
        )
        order = Order.objects.create(
            currency='usd',
            discount=discount,
            tax=tax,
        )
        OrderItem.objects.create(order=order, item=item, quantity=2)

        self.assertEqual(order.subtotal_amount, Decimal('20.00'))
        self.assertEqual(order.discount_amount, Decimal('2.00'))
        self.assertEqual(order.taxable_amount, Decimal('18.00'))
        self.assertEqual(order.tax_amount, Decimal('3.60'))
        self.assertEqual(order.total_amount, Decimal('21.60'))

    def test_fixed_discount_currency_must_match_order_currency(self):
        """Фиксированная скидка должна совпадать с валютой заказа."""
        discount = Discount.objects.create(
            name='Five USD off',
            stripe_coupon_id='coupon_usd_5',
            discount_type=DiscountType.FIXED,
            value=Decimal('5.00'),
            currency='usd',
        )

        with self.assertRaises(ValidationError):
            Order.objects.create(currency='eur', discount=discount)


class TaxModelTests(TestCase):
    """Проверки автосинхронизации и ограничений модели Tax."""

    @patch('api.models.tax.create_stripe_tax_rate_for_tax')
    def test_tax_creates_stripe_tax_rate_automatically(self, mocked_create_tax_rate):
        """При пустом `stripe_tax_rate_id` модель должна создать Tax Rate в Stripe."""
        mocked_create_tax_rate.return_value = 'txr_auto_created'

        tax = Tax.objects.create(
            name='Auto VAT',
            percentage=Decimal('20.00'),
            inclusive=False,
        )

        self.assertEqual(tax.stripe_tax_rate_id, 'txr_auto_created')
        mocked_create_tax_rate.assert_called_once()

    @patch('api.models.tax.create_stripe_tax_rate_for_tax')
    def test_tax_rejects_percentage_change_after_remote_tax_rate_creation(self, mocked_create_tax_rate):
        """Нельзя менять percentage у налога после создания Stripe Tax Rate."""
        mocked_create_tax_rate.return_value = 'txr_locked'

        tax = Tax.objects.create(
            name='Locked VAT',
            percentage=Decimal('20.00'),
            inclusive=False,
        )
        tax.percentage = Decimal('18.00')

        with self.assertRaises(ValidationError):
            tax.save()
