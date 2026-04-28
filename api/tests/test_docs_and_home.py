"""Тесты главной страницы и OpenAPI-документации.

В этих тестах проверяем три ключевых свойства:
1. главная страница рендерится и видит demo-объекты;
2. OpenAPI-схема валидна и содержит ключевые endpoint-ы ТЗ;
3. Swagger UI и Redoc отвечают 200 и ссылаются на ту же схему.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from api.models import Item, Order, OrderItem


class HomePageTests(TestCase):
    """Smoke-тесты для главной страницы проекта."""

    def setUp(self):
        """Создает один товар и один заказ для отображения на главной."""
        self.item = Item.objects.create(
            name='Home Item',
            description='Item shown on the home page.',
            price=Decimal('11.99'),
            currency='usd',
        )
        self.order = Order.objects.create(currency='usd')
        OrderItem.objects.create(order=self.order, item=self.item, quantity=2)

    def test_home_renders_quick_links_and_demo_objects(self):
        """Главная страница должна содержать ссылки на docs, админку и demo-объекты."""
        response = self.client.get(reverse('api:home'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')

        self.assertIn(reverse('admin:index'), body)
        self.assertIn(reverse('api:swagger-ui'), body)
        self.assertIn(reverse('api:redoc-ui'), body)
        self.assertIn(reverse('api:openapi-schema'), body)
        self.assertIn(reverse('api:health-check'), body)
        self.assertIn(self.item.name, body)
        self.assertIn(f'Заказ #{self.order.pk}', body)


class OpenAPISchemaTests(TestCase):
    """Проверки сгенерированной OpenAPI-спецификации."""

    def test_schema_contains_required_paths_and_components(self):
        """Схема должна включать все обязательные ТЗ endpoint-ы и компоненты."""
        response = self.client.get(reverse('api:openapi-schema'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        schema = response.json()

        self.assertEqual(schema['openapi'], '3.1.0')

        paths = schema['paths']
        self.assertIn('/item/{item_id}', paths)
        self.assertIn('/buy/{item_id}', paths)
        self.assertIn('/buy-order/{order_id}', paths)
        self.assertIn('/stripe/webhook/', paths)
        self.assertIn('/health/', paths)

        # У `/buy/{item_id}` должен быть документирован JSON-ответ с `id`.
        buy_response = paths['/buy/{item_id}']['get']['responses']['200']
        schema_ref = buy_response['content']['application/json']['schema']['$ref']
        self.assertEqual(schema_ref, '#/components/schemas/CheckoutSessionId')

        components = schema['components']['schemas']
        self.assertIn('CheckoutSessionId', components)
        self.assertIn('PaymentIntentPayload', components)
        self.assertIn('StripeEvent', components)


class SwaggerAndRedocTests(TestCase):
    """Smoke-тесты UI-страниц документации."""

    def test_swagger_ui_renders_with_schema_url(self):
        """Swagger UI должен ссылаться на `/api/schema/` и отдавать 200."""
        response = self.client.get(reverse('api:swagger-ui'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn(reverse('api:openapi-schema'), body)
        self.assertIn('SwaggerUIBundle', body)

    def test_redoc_renders_with_schema_url(self):
        """Redoc должен ссылаться на ту же схему."""
        response = self.client.get(reverse('api:redoc-ui'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn(reverse('api:openapi-schema'), body)
        self.assertIn('redoc', body)
