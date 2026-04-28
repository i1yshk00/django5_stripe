"""No-op миграция, оставленная для совместимости истории миграций.

Раньше здесь жил backfill, который дозаполнял demo-скидки и налог через
реальный Stripe API на тех базах, где `0005` отработала с пустыми ключами.
Сетевые вызовы убраны из миграций — теперь любой seed Stripe pricing
делается через `python manage.py seed_demo_pricing`.

Миграция оставлена пустой, чтобы не ломать `MIGRATIONS` history.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    """No-op: backfill заменен management-командой `seed_demo_pricing`."""

    dependencies = [
        ('api', '0005_create_valid_pricing_seed'),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
