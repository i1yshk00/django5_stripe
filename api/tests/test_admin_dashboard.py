"""Тесты кастомного dashboard на главной странице административной панели."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import Item, Order, OrderItem, PaymentStatus


class AdminDashboardTests(TestCase):
    """Проверки рендера и базового наполнения dashboard-страницы."""

    def setUp(self):
        """Создает администратора и небольшой набор данных для dashboard."""
        self.user = get_user_model().objects.create_superuser(
            username='dashboard-admin',
            email='admin@example.com',
            password='admin12345',
        )

        item = Item.objects.create(
            name='Dashboard item',
            description='Item visible on dashboard',
            price=Decimal('12.50'),
            currency='usd',
        )
        order = Order.objects.create(
            currency='usd',
            payment_status=PaymentStatus.PAID,
        )
        OrderItem.objects.create(order=order, item=item, quantity=2)

    def test_admin_index_renders_custom_dashboard(self):
        """Главная страница админки должна показывать dashboard вместо app list."""
        self.client.force_login(self.user)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Оперативный дашборд')
        self.assertContains(response, 'Статусы заказов')
        self.assertContains(response, 'Выручка по валютам')
        self.assertContains(response, 'Dashboard item')
        self.assertContains(response, 'Заказ #')
