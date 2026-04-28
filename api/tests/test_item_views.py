"""Тесты HTML-страниц `/item/<id>` и `/order/<id>`."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from api.models import Discount, DiscountType, Item, Order, OrderItem, Tax


@override_settings(
    STRIPE_PUBLISHABLE_KEY='pk_test_item_page',
    STRIPE_SECRET_KEY='sk_test_item_page',
)
class ItemDetailViewTests(TestCase):
    """Проверки рендера обязательной страницы товара."""

    def test_item_detail_renders_product_and_checkout_metadata(self):
        """Страница товара должна содержать данные Item и параметры checkout."""
        item = Item.objects.create(
            name='Demo item',
            description='Demo description',
            price=Decimal('12.34'),
            currency='usd',
        )

        response = self.client.get(reverse('api:item-detail', args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Demo item')
        self.assertContains(response, 'Demo description')
        self.assertContains(response, '1234')
        self.assertContains(response, 'pk_test_item_page')
        self.assertContains(response, reverse('api:buy-item', args=[item.pk]))

    def test_item_detail_returns_404_for_unknown_item(self):
        """Несуществующий товар должен отдавать обычный 404."""
        response = self.client.get(reverse('api:item-detail', args=[999999]))

        self.assertEqual(response.status_code, 404)


@override_settings(
    STRIPE_PUBLISHABLE_KEY='pk_test_order_page',
    STRIPE_SECRET_KEY='sk_test_order_page',
)
class OrderDetailViewTests(TestCase):
    """Проверки HTML-страницы заказа `/order/<id>`."""

    def test_order_detail_renders_items_summary_and_checkout_metadata(self):
        """Страница заказа должна показывать состав и endpoint order checkout."""
        item = Item.objects.create(
            name='Order page item',
            description='Order page description',
            price=Decimal('25.50'),
            currency='usd',
        )
        discount = Discount.objects.create(
            name='Order discount',
            stripe_coupon_id='coupon_order_discount',
            discount_type=DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        tax = Tax.objects.create(
            name='Order tax',
            stripe_tax_rate_id='txr_order_tax',
            percentage=Decimal('20.00'),
            inclusive=False,
        )
        order = Order.objects.create(currency='usd', discount=discount, tax=tax)
        OrderItem.objects.create(order=order, item=item, quantity=2)

        response = self.client.get(reverse('api:order-detail', args=[order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Заказ #{order.pk}')
        self.assertContains(response, 'Order page item')
        self.assertContains(response, '51,00 USD')
        self.assertContains(response, '5,10 USD')
        self.assertContains(response, '9,18 USD')
        self.assertContains(response, '55,08 USD')
        self.assertContains(response, 'pk_test_order_page')
        self.assertContains(response, reverse('api:buy-order', args=[order.pk]))
        self.assertContains(
            response,
            reverse('api:order-payment-intent-detail', args=[order.pk]),
        )

    def test_order_detail_returns_404_for_unknown_order(self):
        """Несуществующий заказ должен отдавать обычный 404."""
        response = self.client.get(reverse('api:order-detail', args=[999999]))

        self.assertEqual(response.status_code, 404)


@override_settings(
    STRIPE_PUBLISHABLE_KEY='pk_test_payment_intent_page',
    STRIPE_SECRET_KEY='sk_test_payment_intent_page',
)
class OrderPaymentIntentDetailViewTests(TestCase):
    """Проверки HTML-страницы bonus-flow на Payment Intent."""

    def test_payment_intent_page_renders_order_summary_and_endpoint(self):
        """Страница Payment Intent должна показать summary и endpoint создания intent."""
        item = Item.objects.create(
            name='Intent page item',
            description='Intent page description',
            price=Decimal('30.00'),
            currency='usd',
        )
        order = Order.objects.create(currency='usd')
        OrderItem.objects.create(order=order, item=item, quantity=2)

        response = self.client.get(
            reverse('api:order-payment-intent-detail', args=[order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stripe Payment Intent')
        self.assertContains(response, 'Intent page item')
        self.assertContains(response, '60,00 USD')
        self.assertContains(response, 'pk_test_payment_intent_page')
        self.assertContains(
            response,
            reverse('api:buy-order-payment-intent', args=[order.pk]),
        )

    def test_payment_intent_page_returns_404_for_unknown_order(self):
        """Несуществующий заказ на Payment Intent странице должен отдавать 404."""
        response = self.client.get(
            reverse('api:order-payment-intent-detail', args=[999999])
        )

        self.assertEqual(response.status_code, 404)
