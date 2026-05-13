"""Middleware: Lokaler Login ist nur aus dem Server-Admin-Subnetz erreichbar.

Hintergrund:
    MaderLunch wird sowohl intern (Mader-Netz) als auch später extern (Internet)
    erreichbar sein. Der lokale Login (Username + Passwort) soll aber NIEMALS
    aus dem Internet erreichbar sein, weil er ein Angriffsvektor für Brute-Force
    ist. Microsoft-Login ist immer erlaubt, da Microsoft die Authentifizierung
    selbst absichert (MFA, Conditional Access etc.).

Diese Middleware:
    - Lässt /accounts/login/ (POST) nur aus dem ALLOWED-Subnetz zu
    - Andere Quellen werden auf /accounts/microsoft/login/ umgeleitet
    - Microsoft-OAuth-Callback und andere allauth-Pfade bleiben uneingeschränkt
    - Lese-Zugriff auf die Login-Seite bleibt erlaubt (sonst sehen Externe nicht
      mal den Microsoft-Button)

Konfiguration:
    LOCAL_LOGIN_ALLOWED_NETWORKS in settings.py — Liste von Subnetzen als Strings,
    z.B. ["10.75.0.0/21"]. Wenn leer, ist der lokale Login von überall erlaubt
    (Dev-Komfort).
"""
from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


def _get_client_ip(request: HttpRequest) -> str | None:
    """Extrahiert die echte Client-IP, ggf. aus X-Forwarded-For (hinter TLS-Proxy).

    Wir vertrauen X-Forwarded-For NUR, wenn settings.SECURE_PROXY_SSL_HEADER
    gesetzt ist — also wenn wir wissen, dass wir hinter einem Reverse Proxy
    sind. Sonst nimmst man die direkte REMOTE_ADDR.
    """
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            # X-Forwarded-For kann eine Liste sein: "client, proxy1, proxy2"
            # Die erste IP ist der echte Client.
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _is_allowed_for_local_login(client_ip: str | None) -> bool:
    """Prüft, ob die Client-IP in einem erlaubten Subnetz für lokalen Login liegt."""
    allowed = getattr(settings, "LOCAL_LOGIN_ALLOWED_NETWORKS", [])
    if not allowed:
        # Leere Konfiguration = überall erlaubt (Dev-Komfort)
        return True
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
        for net_str in allowed:
            if ip in ipaddress.ip_network(net_str, strict=False):
                return True
    except (ValueError, TypeError):
        logger.warning("Konnte Client-IP %r nicht parsen.", client_ip)
        return False
    return False


class RestrictLocalLoginMiddleware:
    """Schränkt lokalen Login auf erlaubte Source-Netze ein."""

    # Pfad, der den lokalen Login bearbeitet (allauth-Standard)
    LOCAL_LOGIN_PATH = "/accounts/login/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        # Nur POSTs auf /accounts/login/ blockieren — die Login-Seite selbst (GET)
        # bleibt erreichbar, sonst sieht der externe User nicht mal den
        # Microsoft-Button.
        if request.method == "POST" and request.path == self.LOCAL_LOGIN_PATH:
            client_ip = _get_client_ip(request)
            if not _is_allowed_for_local_login(client_ip):
                logger.warning(
                    "Lokaler Login-Versuch von nicht erlaubter IP %s blockiert. "
                    "Redirect zur Microsoft-Anmeldung.",
                    client_ip,
                )
                return redirect("/accounts/microsoft/login/")
        return self.get_response(request)
