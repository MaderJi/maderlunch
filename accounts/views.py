"""Eigene Views für MaderLunch-Accounts.

Login, Logout und Passwortwechsel laufen jetzt über django-allauth
(siehe config/urls.py: path("accounts/", include("allauth.urls"))).

Hier bleibt nur die Profil-Seite als Mader-spezifische View.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def profile(request):
    """Zeigt das UserProfile des eingeloggten Users (Mitarbeiter-ID, Standort,
    Kostenstelle, Rolle etc.)."""
    return render(
        request,
        "accounts/profile.html",
        {"profile": getattr(request.user, "profile", None)},
    )
