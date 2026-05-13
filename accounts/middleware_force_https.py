"""Middleware: erzwingt HTTPS-Scheme hinter einem TLS-Proxy, der KEINEN
X-Forwarded-Proto-Header setzt.

Hintergrund:
    Wir betreiben Django hinter einer FortiGate-VIP mit TLS-Offloading.
    FortiOS 7.4 VIPs (server-load-balance) setzen aus historischen Gründen
    NICHT den X-Forwarded-Proto-Header. Folge: Django sieht die Verbindung
    als HTTP statt HTTPS und generiert OAuth-Redirect-URIs mit http:// statt
    https://. Microsoft Entra lehnt diese ab (AADSTS50011).

Lösung:
    Diese Middleware setzt request.is_secure() = True (über META-Manipulation),
    sobald der Host-Header zu einem als TLS-terminiert bekannten Hostname passt.

Konfiguration in settings.py:
    FORCE_SCHEME_HTTPS_FOR_HOSTS = ["lunch.mader.eu", "lunch.intern.mader.eu"]

Sicherheit:
    Greift nur bei den explizit aufgeführten Hosts. Andere Hosts (z.B.
    Direkt-IP-Zugriff aus Server-Admin-Netz) bleiben unverändert HTTP.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class ForceHttpsForKnownHostsMiddleware:
    """Setzt das Scheme auf HTTPS, wenn der Host in der erlaubten Liste ist.

    Funktioniert durch Setzen des HTTP_X_FORWARDED_PROTO META-Eintrags, der
    von Djangos SecurityMiddleware bzw. SECURE_PROXY_SSL_HEADER ausgewertet
    wird.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Liste der Hostnames, bei denen wir wissen: TLS terminiert davor
        self.https_hosts = {
            h.lower() for h in getattr(settings, "FORCE_SCHEME_HTTPS_FOR_HOSTS", [])
        }

    def __call__(self, request):
        if self.https_hosts:
            host = request.get_host().split(":")[0].lower()
            if host in self.https_hosts:
                # X-Forwarded-Proto setzen, damit SECURE_PROXY_SSL_HEADER greift
                request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
