"""Views для отдачи OpenAPI-схемы и UI-документации.

Все три endpoint-а отделены от бизнес-логики:
- `/api/schema/` — OpenAPI 3.1 спецификация в JSON, генерируется при запросе;
- `/api/docs/` — Swagger UI поверх той же схемы;
- `/api/redoc/` — Redoc UI поверх той же схемы.

Swagger UI и Redoc подгружаются с публичного CDN, чтобы не тащить тяжелые
фронтенд-зависимости в Python-проект и не блокировать обновления UI на
своих релизных циклах.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from api.openapi import build_openapi_schema


async def openapi_schema(request):
    """Отдает OpenAPI 3.1 спецификацию в JSON."""
    del request
    return JsonResponse(build_openapi_schema(), json_dumps_params={'ensure_ascii': False})


async def swagger_ui(request):
    """Рендерит страницу Swagger UI поверх `/api/schema/`."""
    return TemplateResponse(
        request,
        'api/swagger_ui.html',
        {'schema_url': reverse('api:openapi-schema')},
    )


async def redoc_ui(request):
    """Рендерит страницу Redoc UI поверх `/api/schema/`."""
    return TemplateResponse(
        request,
        'api/redoc.html',
        {'schema_url': reverse('api:openapi-schema')},
    )
