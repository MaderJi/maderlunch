"""Permission-Helper für MaderLunch.

Verwendung:

    from accounts.permissions import manager_required, admin_required

    @manager_required
    def my_view(request):
        ...

oder als Mixin:

    from accounts.permissions import ManagerRequiredMixin

    class MyView(ManagerRequiredMixin, TemplateView):
        template_name = "..."

Im Template:

    {% if user.profile.is_manager %} ... {% endif %}
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin


def _has_role(user, attr: str) -> bool:
    """True wenn user authentifiziert ist, ein UserProfile hat und die Rollen-Property True ist."""
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    if profile is None:
        return False
    return getattr(profile, attr, False)


# --- Funktions-Decorator ---


def manager_required(view_func):
    """Erlaubt Zugriff für Manager und Admin (hierarchisch)."""

    @wraps(view_func)
    @user_passes_test(lambda u: _has_role(u, "is_manager"))
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    """Erlaubt Zugriff nur für Admin."""

    @wraps(view_func)
    @user_passes_test(lambda u: _has_role(u, "is_app_admin"))
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


# --- CBV-Mixins ---


class ManagerRequiredMixin(UserPassesTestMixin):
    """Mixin für Class-Based Views: Manager oder Admin."""

    def test_func(self) -> bool:
        return _has_role(self.request.user, "is_manager")


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin für Class-Based Views: nur Admin."""

    def test_func(self) -> bool:
        return _has_role(self.request.user, "is_app_admin")
