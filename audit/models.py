from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    """Append-only Audit-Log für sicherheitsrelevante Aktionen.

    Niemals Passwörter oder Tokens in `meta` speichern.
    """

    at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="audit_events",
    )
    actor_repr = models.CharField(max_length=200, blank=True)

    action = models.CharField(max_length=100, db_index=True)

    target_ct = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_id = models.CharField(max_length=64, null=True, blank=True)
    target = GenericForeignKey("target_ct", "target_id")
    target_repr = models.CharField(max_length=200, blank=True)

    meta = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "Audit-Eintrag"
        verbose_name_plural = "Audit-Log"
        ordering = ("-at",)
        indexes = [
            models.Index(fields=["action", "at"]),
        ]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} by {self.actor_repr or 'system'}"
