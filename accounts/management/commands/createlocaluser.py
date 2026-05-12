"""Management-Command: lokalen User mit Initialpasswort anlegen.

Beispiel:
    python manage.py createlocaluser --username m.mueller --first Marie --last Müller \
        --email marie.mueller@mader.eu --role User --employee-id 12345
"""
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import UserProfile
from audit.services import log_event


def _generate_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!#$%&*+-=?@"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        # Mindestanforderungen sicherstellen
        if (any(c.islower() for c in pw)
                and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)
                and any(c in "!#$%&*+-=?@" for c in pw)):
            return pw


class Command(BaseCommand):
    help = "Legt einen lokalen Benutzer an und gibt ein einmaliges Initialpasswort aus."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--first", required=True)
        parser.add_argument("--last", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--role", choices=("User", "Admin"), default="User")
        parser.add_argument("--employee-id", default=None)

    def handle(self, *args, **opts):
        User = get_user_model()
        username = opts["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"Benutzer '{username}' existiert bereits.")

        password = _generate_password()
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=opts["email"],
                first_name=opts["first"],
                last_name=opts["last"],
                password=password,
            )
            UserProfile.objects.create(
                user=user,
                employee_id=opts["employee_id"],
                must_change_password=True,
            )
            grp, _ = Group.objects.get_or_create(name=opts["role"])
            user.groups.add(grp)
            if opts["role"] == "Admin":
                user.is_staff = True
                user.save(update_fields=["is_staff"])

            log_event(
                None, "user.create",
                actor=None,
                target=user,
                meta={"role": opts["role"], "via": "cli"},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Benutzer '{username}' angelegt. Initialpasswort (einmal anzeigen, dann an Nutzer übergeben):"
        ))
        self.stdout.write(self.style.WARNING(password))
