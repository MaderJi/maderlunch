"""User-Profile, Entra-Verknüpfung.

Bewusste Entscheidung:
- Wir benutzen Djangos auth.User unverändert (keine Custom-User-Subklasse),
  weil UserProfile ohnehin alle Mader-spezifischen Felder kapselt.
- Rollen werden hier als role-Feld am UserProfile gepflegt, hierarchisch:
  USER < MANAGER < ADMIN.
- auth_source dokumentiert, ob ein Account lokal oder via Entra angelegt wurde.
"""
from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    USER = "USER", "User"
    MANAGER = "MANAGER", "Manager"
    ADMIN = "ADMIN", "Admin"


class AuthSource(models.TextChoices):
    LOCAL = "LOCAL", "Lokal"
    ENTRA = "ENTRA", "Entra"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    employee_id = models.CharField(
        "Mitarbeiterkennung",
        max_length=32, blank=True, null=True, unique=True,
    )
    location = models.ForeignKey(
        "lunch.Location",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="user_profiles",
        verbose_name="Standort",
    )
    cost_center = models.ForeignKey(
        "billing.CostCenter",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="user_profiles",
        verbose_name="Kostenstelle",
    )
    role = models.CharField(
        "Rolle",
        max_length=10,
        choices=Role.choices,
        default=Role.USER,
        help_text=(
            "Rolle in MaderLunch. Bei Entra-Logins wird die Rolle bei jedem Login "
            "aus dem 'roles'-Claim des ID-Tokens neu gesetzt."
        ),
    )
    auth_source = models.CharField(
        "Anmeldequelle",
        max_length=10,
        choices=AuthSource.choices,
        default=AuthSource.LOCAL,
    )
    must_change_password = models.BooleanField(
        "Passwortänderung erforderlich",
        default=False,
    )
    is_active_employee = models.BooleanField("Aktiv (HR)", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Benutzerprofil"
        verbose_name_plural = "Benutzerprofile"

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username}"

    # --- Hierarchie-Helper ---
    # Die Properties spiegeln die Rollen-Hierarchie:
    # ADMIN kann alles, was MANAGER kann; MANAGER kann alles, was USER kann.

    @property
    def is_manager(self) -> bool:
        """True für MANAGER und ADMIN."""
        return self.role in (Role.MANAGER, Role.ADMIN)

    @property
    def is_app_admin(self) -> bool:
        """True nur für ADMIN.

        Bewusst nicht 'is_admin' genannt, um Verwechslung mit Djangos
        is_staff/is_superuser zu vermeiden.
        """
        return self.role == Role.ADMIN


class EntraIdentity(models.Model):
    """Verknüpfung lokales UserProfile <-> Entra-Identität.

    Wird im Auth-Adapter beim ersten Entra-Login befüllt und bei späteren
    Logins aktualisiert (last_login_at, ggf. upn falls geändert).
    """
    profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="entra_identity",
    )
    tenant_id = models.CharField("Tenant ID", max_length=64)
    object_id = models.CharField(
        "Entra Object ID (oid)",
        max_length=64,
        help_text="Eindeutige, unveränderliche User-ID im Tenant.",
    )
    upn_at_link = models.CharField(
        "UPN bei Verknüpfung",
        max_length=254,
        help_text="UPN/E-Mail zum Zeitpunkt der ersten Verknüpfung. Nur zu Audit-Zwecken.",
    )
    last_roles_claim = models.JSONField(
        "Letzte Rollen aus Token",
        default=list, blank=True,
        help_text="Roh-Inhalt des 'roles'-Claims beim letzten Login. Für Debugging.",
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Entra-Identität"
        verbose_name_plural = "Entra-Identitäten"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "object_id"],
                name="uniq_entra_tenant_object",
            ),
        ]
    def __str__(self) -> str:
        return f"Entra: {self.upn_at_link} → {self.profile}"
