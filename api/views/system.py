"""Системные HTTP-endpoint-ы проекта.

В этом модуле держим только технические маршруты, которые не относятся
напрямую к пользовательскому checkout-flow, но нужны для эксплуатации
приложения в production:
- healthcheck;
- в дальнейшем сюда можно добавлять readiness/liveness probes и похожие вещи.
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def _probe_default_database() -> None:
    """Проверяет, что база данных доступна и принимает простые запросы.

    Проверка intentionally минимальна:
    - не читает прикладные таблицы;
    - не зависит от содержимого БД;
    - достаточно хорошо показывает, что соединение с основным database backend
      живо и приложение сможет выполнять реальные ORM-операции.
    """
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()


async def health_check(request):
    """Возвращает состояние приложения и доступность основной базы данных.

    Ответ полезен сразу в нескольких сценариях:
    - Docker healthcheck;
    - внешние load balancer / ingress probes;
    - ручная диагностика после деплоя.

    Формат ответа намеренно простой JSON, чтобы его было удобно читать и людям,
    и автоматическим системам.
    """
    try:
        await sync_to_async(_probe_default_database, thread_sensitive=True)()
    except OperationalError as exc:
        return JsonResponse(
            {
                'status': 'error',
                'database': 'unavailable',
                'details': str(exc),
            },
            status=503,
        )

    return JsonResponse(
        {
            'status': 'ok',
            'database': 'ok',
        }
    )
