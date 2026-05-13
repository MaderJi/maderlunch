"""Migration: Rollen am UserProfile, EntraIdentity erweitern, EntraGroupMapping entfernen.

Wichtige Hinweise:
- Die Nummer (0002_...) setzt voraus, dass die initiale accounts-Migration 0001 heißt.
  Wenn deine bestehende erste Migration anders heißt, dependencies entsprechend anpassen.
- Diese Migration entfernt EntraGroupMapping ohne Datenmigration — wir gehen davon aus,
  dass das alte Modell noch nicht produktiv genutzt wurde. Sollte es schon Daten geben,
  vorher per Hand sichern oder Code anpassen.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
    ]

    operations = [
        # --- UserProfile: neue Felder role und auth_source ---
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[("USER", "User"), ("MANAGER", "Manager"), ("ADMIN", "Admin")],
                default="USER",
                help_text=(
                    "Rolle in MaderLunch. Bei Entra-Logins wird die Rolle bei jedem Login "
                    "aus dem 'roles'-Claim des ID-Tokens neu gesetzt."
                ),
                max_length=10,
                verbose_name="Rolle",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="auth_source",
            field=models.CharField(
                choices=[("LOCAL", "Lokal"), ("ENTRA", "Entra")],
                default="LOCAL",
                max_length=10,
                verbose_name="Anmeldequelle",
            ),
        ),

        # --- EntraIdentity: neue Felder last_roles_claim und last_login_at ---
        migrations.AddField(
            model_name="entraidentity",
            name="last_roles_claim",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Roh-Inhalt des 'roles'-Claims beim letzten Login. Für Debugging.",
                verbose_name="Letzte Rollen aus Token",
            ),
        ),

        # --- EntraGroupMapping entfernen ---
        # War für die ursprüngliche "Group Claims"-Variante gedacht (Variante A).
        # Da wir auf App Roles umgestellt haben, nicht mehr nötig.
        migrations.DeleteModel(
            name="EntraGroupMapping",
        ),
    ]
