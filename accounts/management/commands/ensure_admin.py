import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create the admin account from the ADMIN_USERNAME, ADMIN_PASSWORD and "
        "ADMIN_EMAIL environment variables if it doesn't exist yet. Useful on hosts "
        "without shell access. An existing account is never changed."
    )

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        email = os.environ.get("ADMIN_EMAIL", "").strip()

        if not username or not password:
            self.stdout.write("ADMIN_USERNAME / ADMIN_PASSWORD not set; skipping admin creation.")
            return

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(f"Admin account '{username}' already exists; nothing to do.")
            return

        candidate = user_model(username=username, email=email)
        try:
            validate_password(password, user=candidate)
        except ValidationError as error:
            raise CommandError("ADMIN_PASSWORD is too weak: " + " ".join(error.messages))

        user_model.objects.create_superuser(
            username=username, email=email, password=password, is_approved=True
        )
        self.stdout.write(self.style.SUCCESS(f"Created admin account '{username}'."))
