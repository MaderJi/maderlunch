"""django-allauth Adapter für MaderLunch.

Zwei Adapter:

1. MaderAccountAdapter — für lokale Konten.
2. MaderEntraSocialAdapter — für Entra-Logins.

Rollen-Auflösung:
   allauth-Microsoft liefert leider keinen 'groups'-Claim direkt — der
   Microsoft-Provider holt nur Graph-Profildaten via /me, nicht das ID-Token
   mit App-Claims. Daher rufen wir die Gruppen explizit per Graph API ab:
   GET https://graph.microsoft.com/v1.0/me/memberOf

   Voraussetzungen in Entra:
   - Delegated Permission "GroupMember.Read.All" mit Admin Consent
   - SCOPE in SOCIALACCOUNT_PROVIDERS enthält "GroupMember.Read.All"

   Die Group-Object-IDs werden gegen ENTRA_GROUP_MAP gematched, höchste Rolle
   gewinnt. Fall-Back: USER, wenn keine Match.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from decouple import config
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import AuthSource, EntraIdentity, Role, UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Mapping: Entra Group Object-ID -> internes Role-Enum
# ---------------------------------------------------------------------------
ENTRA_GROUP_MAP: dict[str, Role] = {
    config("ENTRA_GROUP_ADMIN", default=""): Role.ADMIN,
    config("ENTRA_GROUP_MANAGER", default=""): Role.MANAGER,
    config("ENTRA_GROUP_USER", default=""): Role.USER,
}
ENTRA_GROUP_MAP = {k: v for k, v in ENTRA_GROUP_MAP.items() if k}

ROLE_PRIORITY: list[Role] = [Role.ADMIN, Role.MANAGER, Role.USER]

GRAPH_MEMBEROF_URL = "https://graph.microsoft.com/v1.0/me/memberOf?$select=id"
GRAPH_TIMEOUT_SECONDS = 10


def resolve_role_from_groups(group_ids: Iterable[str]) -> Role:
    """Höchste Rolle aus Group-GUIDs ableiten. Fallback: Role.USER."""
    user_group_ids = set(group_ids or [])
    for candidate in ROLE_PRIORITY:
        for guid, role in ENTRA_GROUP_MAP.items():
            if role == candidate and guid in user_group_ids:
                return candidate
    return Role.USER


def _fetch_user_groups(access_token: str) -> list[str]:
    """Holt die Group-Object-IDs des aktuellen Users via Microsoft Graph API.

    Behandelt Pagination (@odata.nextLink) und Fehler defensiv.
    """
    if not access_token:
        logger.warning("Kein Access Token, kann keine Gruppen holen.")
        return []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    group_ids: list[str] = []
    next_url: str | None = GRAPH_MEMBEROF_URL

    try:
        while next_url:
            resp = requests.get(next_url, headers=headers, timeout=GRAPH_TIMEOUT_SECONDS)
            if resp.status_code != 200:
                logger.error(
                    "Graph /me/memberOf fehlgeschlagen: HTTP %s — %s",
                    resp.status_code, resp.text[:300],
                )
                break

            data = resp.json()
            for item in data.get("value", []):
                gid = item.get("id")
                if gid:
                    group_ids.append(gid)

            next_url = data.get("@odata.nextLink")
    except requests.RequestException:
        logger.exception("Netzwerk-Fehler beim Graph-Call /me/memberOf.")

    return group_ids


def _sync_role_and_flags(user, profile: UserProfile, sociallogin) -> Role:
    """Setzt Rolle und Django-Flags basierend auf Microsoft Graph-Mitgliedschaft."""
    token = getattr(sociallogin, "token", None)
    access_token = token.token if token else ""
    groups_claim = _fetch_user_groups(access_token)
    resolved_role = resolve_role_from_groups(groups_claim)

    profile.role = resolved_role
    profile.auth_source = AuthSource.ENTRA
    profile.save(update_fields=["role", "auth_source", "updated_at"])

    is_admin = (resolved_role == Role.ADMIN)
    if user.is_staff != is_admin or user.is_superuser != is_admin:
        user.is_staff = is_admin
        user.is_superuser = is_admin
        user.save(update_fields=["is_staff", "is_superuser"])

    logger.info(
        "Entra-Login synchronisiert: user=%s role=%s is_staff=%s groups_count=%d",
        user.username, resolved_role, is_admin, len(groups_claim),
    )
    return resolved_role


def _upsert_entra_identity(profile: UserProfile, sociallogin) -> EntraIdentity:
    """Legt EntraIdentity an oder aktualisiert bestehende Felder."""
    extra = sociallogin.account.extra_data or {}
    oid = extra.get("id") or extra.get("oid") or sociallogin.account.uid
    upn = extra.get("userPrincipalName") or extra.get("mail") or sociallogin.user.email or ""

    # Tenant-ID aus dem Access Token holen (Graph-Daten enthalten sie nicht)
    tid = ""
    token = getattr(sociallogin, "token", None)
    if token and token.token:
        try:
            import jwt
            decoded = jwt.decode(
                token.token,
                options={"verify_signature": False, "verify_aud": False},
            )
            tid = decoded.get("tid", "")
        except Exception:
            logger.exception("Konnte tid nicht aus Access Token lesen.")

    # Aktuelle Gruppen für Audit-Spur
    access_token = token.token if token else ""
    groups_claim = _fetch_user_groups(access_token) if access_token else []

    identity, _created = EntraIdentity.objects.update_or_create(
        profile=profile,
        defaults={
            "tenant_id": tid,
            "object_id": oid,
            "upn_at_link": upn,
            "last_roles_claim": groups_claim,
            "last_login_at": timezone.now(),
        },
    )
    return identity


# ---------------------------------------------------------------------------
# Lokale Konten
# ---------------------------------------------------------------------------
class MaderAccountAdapter(DefaultAccountAdapter):
    """Lokale Konten: keine Self-Registration."""

    def is_open_for_signup(self, request) -> bool:
        return False


# ---------------------------------------------------------------------------
# Entra (Social Login)
# ---------------------------------------------------------------------------
class MaderEntraSocialAdapter(DefaultSocialAccountAdapter):
    """Adapter für den Microsoft/Entra Login."""

    def is_open_for_signup(self, request, sociallogin) -> bool:
        return True

    def pre_social_login(self, request, sociallogin):
        """Wird bei JEDEM Login aufgerufen.

        1. E-Mail-Konflikt-Auflösung
        2. Rollen-Sync für bereits bekannte User
        """
        # E-Mail-Konflikt-Auflösung
        if not sociallogin.is_existing:
            email = (sociallogin.user.email or "").strip().lower()
            if email:
                try:
                    existing = User.objects.get(email__iexact=email)
                    sociallogin.connect(request, existing)
                    logger.info(
                        "Entra-Account mit lokalem User '%s' verknüpft.",
                        existing.username,
                    )
                except User.DoesNotExist:
                    pass
                except User.MultipleObjectsReturned:
                    logger.warning(
                        "Mehrere lokale User mit E-Mail %s, Verknüpfung abgebrochen.",
                        email,
                    )

        # Rollen-Sync für bekannte User (bei neuen läuft save_user gleich danach)
        user = sociallogin.user
        if user.pk:
            with transaction.atomic():
                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={"auth_source": AuthSource.ENTRA},
                )
                _sync_role_and_flags(user, profile, sociallogin)
                _upsert_entra_identity(profile, sociallogin)

    def populate_user(self, request, sociallogin, data):
        """JIT-Provisioning: User-Felder initial setzen."""
        user = super().populate_user(request, sociallogin, data)
        if not user.username and user.email:
            user.username = user.email
        return user

    def save_user(self, request, sociallogin, form=None):
        """Wird beim ersten Login eines unbekannten Users aufgerufen."""
        with transaction.atomic():
            user = super().save_user(request, sociallogin, form)
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={"auth_source": AuthSource.ENTRA},
            )
            _sync_role_and_flags(user, profile, sociallogin)
            _upsert_entra_identity(profile, sociallogin)
        return user
