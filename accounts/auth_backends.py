"""Entra-OIDC-Backend (vorbereitet, nicht im MVP aktiv).

Aktivierung in Phase 2:
1. settings: OIDC_ENABLED=True und mozilla_django_oidc in INSTALLED_APPS
2. AUTHENTICATION_BACKENDS um diesen Backend ergänzen
3. urls: path("oidc/", include("mozilla_django_oidc.urls"))

Verknüpfungslogik:
- Stabiler Schlüssel ist (tenant_id, object_id), NICHT die E-Mail.
- Bei Erstanmeldung: Versuch, anhand E-Mail ein bestehendes UserProfile zu finden
  und EntraIdentity anzulegen ("Verknüpfung").
- Existiert kein Profil: Login wird abgelehnt. Keine Auto-Anlage im MVP.
"""
from __future__ import annotations

from django.utils import timezone

try:
    from mozilla_django_oidc.auth import OIDCAuthenticationBackend
except ImportError:  # paket vorhanden, aber Import-Fehler bei deaktiviertem OIDC vermeiden
    OIDCAuthenticationBackend = object  # type: ignore

from accounts.models import EntraIdentity, UserProfile
from audit.services import log_event


class EntraOIDCBackend(OIDCAuthenticationBackend):  # type: ignore[misc]
    """Custom-Backend für Microsoft Entra ID."""

    def filter_users_by_claims(self, claims):
        oid = claims.get("oid")
        tid = claims.get("tid")
        if not oid or not tid:
            return self.UserModel.objects.none()
        try:
            ident = EntraIdentity.objects.select_related("profile__user").get(
                tenant_id=tid, object_id=oid
            )
            return self.UserModel.objects.filter(pk=ident.profile.user.pk)
        except EntraIdentity.DoesNotExist:
            return self.UserModel.objects.none()

    def create_user(self, claims):
        """Erstanmeldung — versuche Verknüpfung per E-Mail, sonst ablehnen."""
        oid = claims.get("oid")
        tid = claims.get("tid")
        upn = (claims.get("preferred_username") or claims.get("email") or "").lower()

        if not (oid and tid and upn):
            return None

        # Existiert ein lokales Profil mit dieser E-Mail?
        candidate = (
            UserProfile.objects.select_related("user")
            .filter(user__email__iexact=upn, is_active_employee=True)
            .first()
        )
        if not candidate:
            log_event(
                None, "entra.first_login",
                meta={"result": "no_local_profile", "upn": upn, "tid": tid},
            )
            return None

        EntraIdentity.objects.create(
            profile=candidate,
            tenant_id=tid,
            object_id=oid,
            upn_at_link=upn,
            last_login_at=timezone.now(),
        )
        log_event(
            None, "entra.link",
            actor=candidate.user,
            target=candidate,
            meta={"upn": upn},
        )
        return candidate.user

    def update_user(self, user, claims):
        ident = EntraIdentity.objects.filter(profile__user=user).first()
        if ident:
            ident.last_login_at = timezone.now()
            ident.save(update_fields=["last_login_at"])
        return user
