"""Data migration для создания встроенного администратора проекта.

Эта миграция оставляет быстрый вход в backoffice после первого `migrate`,
чтобы тестовый стенд можно было проверить без ручного создания пользователя.
"""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_default_admin_user(apps, schema_editor):
    """Создает или обновляет встроенного superuser `admin`.

    Используем `update_or_create`, чтобы миграция оставалась идемпотентной и
    не зависела от того, поднимался ли стенд раньше.
    """
    del schema_editor

    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    UserModel = apps.get_model(app_label, model_name)
    username_field_name = getattr(UserModel, 'USERNAME_FIELD', 'username')

    UserModel.objects.update_or_create(
        **{username_field_name: 'admin'},
        defaults={
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
            'password': make_password('admin12345'),
        },
    )


class Migration(migrations.Migration):
    """Добавляет встроенного администратора для быстрого входа в админку."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            create_default_admin_user,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
