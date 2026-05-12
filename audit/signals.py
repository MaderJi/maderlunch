from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .services import log_event


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    log_event(request, "user.login.success", actor=user, target=user)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is None:
        return
    log_event(request, "user.logout", actor=user, target=user)


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username", "")
    log_event(request, "user.login.failure", meta={"username_attempt": username})
