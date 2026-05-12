"""Zentraler Service für AuditLog-Einträge.

Verwendung:
    from audit.services import log_event
    log_event(request, "order.cancel.user", target=order, meta={"reason": "..."})
"""
from __future__ import annotations

from typing import Any, Optional

from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest

from .models import AuditLog

# Whitelist erlaubter Action-Keys — verhindert Tippfehler-Wildwuchs.
ACTIONS = {
    # Auth
    "user.login.success",
    "user.login.failure",
    "user.logout",
    "user.create",
    "user.disable",
    "user.role_change",
    "user.password_reset",
    "user.password_change_self",
    "user.password_set",
    # Entra
    "entra.first_login",
    "entra.link",
    # Lunch
    "order.place",
    "order.cancel.user",
    "order.cancel.admin",
    "order.serve",
    "guest_order.place",
    "guest_order.cancel.admin",
    "guest_order.serve",
    "mealplan.publish",
    "mealplan.update",
    # Billing / Stammdaten
    "subsidy.create",
    "subsidy.update",
    "export.csv",
    # System
    "admin.access",
}

# Felder, die NIE in meta erscheinen dürfen
_FORBIDDEN_META_KEYS = {
    "password", "password1", "password2",
    "token", "access_token", "refresh_token", "id_token",
    "secret", "client_secret",
    "authorization", "cookie",
}


def _scrub(meta: dict[str, Any]) -> dict[str, Any]:
    if not meta:
        return {}
    out = {}
    for k, v in meta.items():
        if k.lower() in _FORBIDDEN_META_KEYS:
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = _scrub(v)
        else:
            out[k] = v
    return out


def _client_ip(request: Optional[HttpRequest]) -> Optional[str]:
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(
    request: Optional[HttpRequest],
    action: str,
    *,
    actor=None,
    target: Any = None,
    meta: Optional[dict] = None,
) -> AuditLog:
    if action not in ACTIONS:
        # In Dev werfen wir, in Prod loggen wir nur — Pragmatismus über Strenge.
        # Hier strikt: verhindert Tippfehler.
        raise ValueError(f"Unknown audit action: {action!r}")

    if actor is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        actor = request.user

    actor_repr = ""
    if actor is not None:
        actor_repr = getattr(actor, "username", "") or str(actor)

    target_ct = None
    target_id = None
    target_repr = ""
    if target is not None:
        target_ct = ContentType.objects.get_for_model(target.__class__)
        target_id = str(getattr(target, "pk", ""))
        target_repr = str(target)[:200]

    return AuditLog.objects.create(
        actor_user=actor if actor and getattr(actor, "is_authenticated", False) else None,
        actor_repr=actor_repr,
        action=action,
        target_ct=target_ct,
        target_id=target_id,
        target_repr=target_repr,
        meta=_scrub(meta or {}),
        ip_address=_client_ip(request),
        request_id=getattr(request, "request_id", "") if request else "",
    )
