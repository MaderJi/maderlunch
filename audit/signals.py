"""Audit-Signal-Handler für Authentifizierungs-Events.

Login/Logout: Django-Standard-Signale (funktionieren auch mit allauth, da allauth
diese Standard-Signale feuert).

Passwortwechsel: zwei Quellen
  1. Djangos Form-basierte Views (vorher in accounts/views.py.password_change)
  2. allauth's eigene Passwort-Change-View
Beide werden hier durch unterschiedliche Signale abgebildet.
"""
from allauth.account.signals import password_changed, password_set
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .services import log_event


@receiver(user_logged_in)
def on_login_success(sender, request, user, **kwargs):
    log_event(request, "user.login.success", actor=user, target=user)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    # user kann None sein bei "nicht-eingeloggter Logout-Aufruf"
    if user is not None:
        log_event(request, "user.logout", actor=user, target=user)


@receiver(user_login_failed)
def on_login_failure(sender, credentials, request=None, **kwargs):
    username = credentials.get("username") if credentials else None
    log_event(request, "user.login.failure", meta={"username_attempt": username})


# --- AUTH-PATCH: allauth-spezifische Signale ---

@receiver(password_changed)
def on_password_changed(sender, request, user, **kwargs):
    """allauth feuert das, wenn ein User sein Passwort über /accounts/password/change/ ändert."""
    log_event(request, "user.password_change_self", actor=user, target=user)


@receiver(password_set)
def on_password_set(sender, request, user, **kwargs):
    """allauth feuert das, wenn ein User zum ersten Mal ein Passwort setzt
    (z.B. nachdem er nur über Social-Login eingeloggt war).

    Für Mader vermutlich selten relevant, aber Audit-Spur ist gut.
    """
    log_event(request, "user.password_set", actor=user, target=user)
