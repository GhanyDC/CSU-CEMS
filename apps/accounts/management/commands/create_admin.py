"""
Management command to create an admin user with an AdminProfile.

Usage:
    python manage.py create_admin --username eb_head --role electoral_board_head --display-name "VP Juan Dela Cruz"
    python manage.py create_admin --username operator1 --role electoral_board_operator --display-name "Operator One" --email op1@example.edu
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import AdminProfile, AdminRole


class Command(BaseCommand):
    help = "Create an admin user with a role-based AdminProfile."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Admin login username.")
        parser.add_argument(
            "--role",
            required=True,
            choices=[r.value for r in AdminRole],
            help="Admin role.",
        )
        parser.add_argument(
            "--display-name", required=True, help="Human-readable name for audit/UI."
        )
        parser.add_argument("--email", default="", help="Optional email address.")
        parser.add_argument(
            "--password",
            default=None,
            help="Password (prompted interactively if omitted).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        role = options["role"]
        display_name = options["display_name"]
        email = options["email"]
        password = options["password"]

        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        if not password:
            import getpass

            password = getpass.getpass(f"Password for {username}: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise CommandError("Passwords do not match.")

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters.")

        try:
            validate_password(password)
        except ValidationError as e:
            raise CommandError("Password validation failed: " + "; ".join(e.messages))

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        user.is_staff = False  # No Django admin site access by default
        user.save()

        profile = AdminProfile.objects.create(
            user=user,
            role=role,
            display_name=display_name,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created admin '{username}' with role '{profile.get_role_display()}'."
            )
        )
