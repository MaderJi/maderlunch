from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


# Pfade, die auch bei must_change_password=True erreichbar bleiben müssen.
_ALLOWED_PATH_PREFIXES = (
    "/static/",
    "/healthz/",
    "/admin/jsi18n/",
)


def _allowed_named_views(request):
    """Pfade, die wir per reverse auflösen — robust gegen URL-Änderungen."""
    paths = []
    for name in (
        "account_change_password",
        "account_change_password",
        "account_logout",
    ):
        try:
            paths.append(reverse(name))
        except NoReverseMatch:
            continue
    return paths


class ForcePasswordChangeMiddleware:
    """Wenn UserProfile.must_change_password gesetzt ist, wird jeder Request
    auf die Passwort-Ändern-Seite umgeleitet — bis das Passwort geändert wurde.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile and profile.must_change_password:
                allowed = _allowed_named_views(request)
                if not (
                    request.path in allowed
                    or any(request.path.startswith(p) for p in _ALLOWED_PATH_PREFIXES)
                ):
                    return redirect("account_change_password")
        return self.get_response(request)
