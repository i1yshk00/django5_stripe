"""No-op миграция, оставленная для совместимости истории миграций.

Раньше эта миграция делала реальные сетевые вызовы в Stripe API при
`migrate`, чтобы создать demo `Coupon` и `Tax Rate` и привязать их к
demo-заказу. Это было плохо по нескольким причинам:

- миграции должны быть детерминированы и воспроизводимы, а сетевые вызовы
  ломают и то и другое;
- `migrate` в CI и Docker-build стартовал бы с реальной сетью до Stripe;
- падения Stripe или проблемы с DNS превращались в падения деплоя.

Логика создания demo pricing-объектов вынесена в management-команду
`python manage.py seed_demo_pricing` (см. `api/management/commands/`).
Миграция оставлена пустой, чтобы не ломать `MIGRATIONS` history на тех
базах, где она уже была применена.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    """No-op: реальный seed Stripe pricing вынесен в management-команду."""

    dependencies = [
        ('api', '0004_normalize_demo_seed_data'),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
