"""User-Profile, Entra-Verknüpfung.

Bewusste Entscheidung:
- Wir benutzen Djangos auth.User unverändert (keine Custom-User-Subklasse),
  weil UserProfile ohnehin alle Mader-spezifischen Felder kapselt.
- Eine spätere Migration auf Custom User wäre teurer als der hier vermiedene Komfort.
"""
from django.conf import settings
from django.db import models


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


class EntraIdentity(models.Model):
    """Verknüpfung lokales UserProfile <-> Entra-Identität.

    Stabile Schlüssel: tenant_id + object_id. UPN/E-Mail ist informativ.
    """
    profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="entra_identity",
    )
    tenant_id = models.CharField("Entra Tenant-ID", max_length=64)
    object_id = models.CharField("Entra Object-ID", max_length=64)
    upn_at_link = models.EmailField("UPN beim Verknüpfen", blank=True)
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
        return f"{self.profile.user.username} ({self.upn_at_link})"


class EntraGroupMapping(models.Model):
    """Optional: Mapping Entra-Group-Object-ID -> Django-Group.

    Im MVP nicht aktiv ausgewertet — Tabelle existiert für Phase 2/3.
    """
    entra_group_object_id = models.CharField("Entra Group Object-ID", max_length=64, unique=True)
    django_group = models.ForeignKey(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="entra_mappings",
    )
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Entra-Gruppen-Mapping"
        verbose_name_plural = "Entra-Gruppen-Mappings"

    def __str__(self) -> str:
        return f"{self.entra_group_object_id} → {self.django_group.name}"
