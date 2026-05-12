"""Management-Command: lokalen User mit Initialpasswort anlegen.

Beispiel:
    python manage.py createlocaluser \\
        --username m.mueller --first Marie --last Müller \\
        --email marie.mueller@mader.eu --role MANAGER --employee-id 12345

Das generierte Initialpasswort wird einmal auf der Konsole ausgegeben.
must_change_password=True erzwingt einen Passwortwechsel beim ersten Login.
"""
from __future__ import annotations

import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AuthSource, Role, UserProfile

User = get_user_model()


def _generate_password(length: int = 14) -> str:
    """Erzeugt ein zufälliges Initialpasswort.

    Bewusst keine Sonderzeichen, die in Terminals/Copy&Paste oft Probleme machen
    (z.B. '\\', '$', '"'). Trotzdem hinreichend stark durch Länge und Entropie.
    """
    alphabet = string.ascii_letters + string.digits + "!@#%&*-_+="
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Lokalen MaderLunch-User mit Initialpasswort anlegen."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="z.B. m.mueller")
        parser.add_argument("--first", required=True, help="Vorname")
        parser.add_argument("--last", required=True, help="Nachname")
        parser.add_argument("--email", required=True, help="E-Mail-Adresse")
        parser.add_argument(
            "--role",
            required=False,
            default=Role.USER,
            choices=[r.value for r in Role],
            help="Rolle (USER, MANAGER, ADMIN). Default: USER.",
        )
        parser.add_argument("--employee-id", required=False, help="Mitarbeiterkennung")
        parser.add_argument(
            "--no-force-password-change",
            action="store_true",
            help="must_change_password NICHT setzen (für Break-Glass-Konten).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' existiert bereits.")
        if User.objects.filter(email__iexact=options["email"]).exists():
            raise CommandError(f"E-Mail '{options['email']}' wird bereits verwendet.")

        password = _generate_password()
        role = options["role"]

        user = User.objects.create_user(
            username=username,
            email=options["email"],
            password=password,
            first_name=options["first"],
            last_name=options["last"],
        )

        # ADMIN bekommt is_staff/is_superuser auch lokal — damit Break-Glass-Konten
        # ohne Entra funktionieren.
        if role == Role.ADMIN:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])

        UserProfile.objects.create(
            user=user,
            employee_id=options.get("employee_id") or None,
            role=role,
            auth_source=AuthSource.LOCAL,
            must_change_password=not options["no_force_password_change"],
        )

        self.stdout.write(self.style.SUCCESS(
            f"User '{username}' (Rolle: {role}) angelegt.\n"
            "Initialpasswort (einmal anzeigen, dann an Nutzer übergeben):"
        ))
        self.stdout.write(self.style.WARNING(password))
        if role == Role.ADMIN:
            self.stdout.write(self.style.NOTICE(
                "\nHinweis: ADMIN-Rolle wurde gesetzt → is_staff=True, is_superuser=True. "
                "Dieses Konto hat vollen Django-Admin-Zugriff."
            ))
