from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection


def healthz(request):
    db_ok = "ok"
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:  # noqa: BLE001
        db_ok = "fail"
    status = 200 if db_ok == "ok" else 503
    return JsonResponse({"status": "ok" if db_ok == "ok" else "degraded", "db": db_ok}, status=status)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("accounts/", include("accounts.urls")),
    path("billing/", include("billing.urls")),
    path("", include("lunch.urls")),  # Dashboard auf "/"
    # path("oidc/", include("mozilla_django_oidc.urls")),  # Phase 2
]
