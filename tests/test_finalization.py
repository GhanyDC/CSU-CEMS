"""
Tests for Final System Finalization Run 02.

Covers:
- Health check endpoint
- Password validation in create_admin command
- Deployment configuration sanity
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client


@pytest.mark.django_db
class TestHealthEndpoint:
    """Health check endpoint tests."""

    def test_health_returns_200(self):
        client = Client()
        response = client.get("/api/health/")
        assert response.status_code == 200

    def test_health_returns_json(self):
        client = Client()
        response = client.get("/api/health/")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_allows_get(self):
        client = Client()
        response = client.get("/api/health/")
        assert response.status_code == 200

    def test_health_no_auth_required(self):
        """Health endpoint must not require authentication."""
        client = Client()
        response = client.get("/api/health/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestCreateAdminPasswordValidation:
    """Ensure create_admin enforces Django password validators."""

    def test_common_password_rejected(self):
        with pytest.raises(CommandError, match="[Pp]assword"):
            call_command(
                "create_admin",
                username="testadmin1",
                role="electoral_board_operator",
                display_name="Test Admin",
                password="password",  # common password
            )

    def test_numeric_password_rejected(self):
        with pytest.raises(CommandError, match="[Pp]assword"):
            call_command(
                "create_admin",
                username="testadmin2",
                role="electoral_board_operator",
                display_name="Test Admin",
                password="12345678",  # entirely numeric
            )

    def test_short_password_rejected(self):
        with pytest.raises(CommandError, match="[Pp]assword"):
            call_command(
                "create_admin",
                username="testadmin3",
                role="electoral_board_operator",
                display_name="Test Admin",
                password="abc",  # too short
            )

    def test_strong_password_accepted(self):
        call_command(
            "create_admin",
            username="testadmin4",
            role="electoral_board_operator",
            display_name="Test Admin",
            password="SecureP@ss2026!x",
        )
        from django.contrib.auth.models import User
        assert User.objects.filter(username="testadmin4").exists()

    def test_duplicate_username_rejected(self):
        call_command(
            "create_admin",
            username="dupuser",
            role="electoral_board_operator",
            display_name="First",
            password="SecureP@ss2026!y",
        )
        with pytest.raises(CommandError, match="already exists"):
            call_command(
                "create_admin",
                username="dupuser",
                role="electoral_board_operator",
                display_name="Second",
                password="SecureP@ss2026!z",
            )
