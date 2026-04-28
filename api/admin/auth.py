"""Адаптация встроенных моделей пользователей и групп под Unfold.

По документации Unfold стандартные админ-классы `UserAdmin` и `GroupAdmin`
работают, но визуально выбиваются из нового интерфейса. Поэтому мы снимаем
стандартную регистрацию и регистрируем их повторно с использованием
`unfold.admin.ModelAdmin`.
"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User

from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


try:
    # Django по умолчанию уже зарегистрировал встроенную модель пользователя.
    # Для перехода на Unfold нужно снять эту регистрацию и навесить свою.
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    # То же самое делаем для групп прав доступа.
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Unfold-совместимая админка встроенной модели пользователя.

    Мы оставляем привычное поведение стандартного Django `UserAdmin`, но
    подменяем формы на unfold-совместимые, чтобы интерфейс не выпадал из общего
    визуального слоя новой админки.
    """

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Unfold-совместимая админка встроенной модели группы."""
