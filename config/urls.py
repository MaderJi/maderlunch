"""MaderLunch URL-Konfiguration.

AUTH-PATCH 2026-05:
- /accounts/* wird komplett von django-allauth bedient
  (Login, Logout, Microsoft-Login, Passwortwechsel)
- /accounts/profile/ ist eine Mader-spezifische View (siehe accounts/views.py)
- accounts/urls.py existiert nicht mehr
"""
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # AUTH-PATCH: allauth übernimmt /accounts/login/, /logout/, /password/change/,
    # /microsoft/login/, /microsoft/login/callback/ etc.
    path("accounts/", include("allauth.urls")),

    # Mader-spezifische Account-View — bewusst NACH allauth-Include,
    # damit allauth seine eigenen URLs registriert und wir nur 'profile/' draufpacken.
    path("accounts/profile/", accounts_views.profile, name="profile"),

    # MaderLunch-eigene Apps
    path("", include("lunch.urls")),
    path("billing/", include("billing.urls")),
]
