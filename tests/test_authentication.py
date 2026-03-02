"""
Tests for student authentication.

Covers:
- Successful login
- Failed login (wrong DOB)
- Failed attempts counter increment
- Account locking after threshold
- Generic error messages
- Audit log creation
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import Student
from apps.audit.models import AuditLog


@pytest.mark.django_db
class TestStudentAuthentication:
    """Test suite for student_login view."""

    def setup_method(self) -> None:
        self.client = Client(enforce_csrf_checks=False)
        self.url = "/api/auth/login/"
        self.student = Student.objects.create(
            student_id="AUTH001",
            full_name="Test User",
            date_of_birth=date(2000, 1, 1),
            course="Engineering",
            year=2,
        )

    def _post_login(self, student_id: str, dob: str) -> object:
        """Helper to POST a login request."""
        return self.client.post(
            self.url,
            data=json.dumps(
                {"student_id": student_id, "date_of_birth": dob}
            ),
            content_type="application/json",
        )

    # ---- Success ----

    def test_successful_login(self) -> None:
        """Correct credentials return 200 and student data."""
        response = self._post_login("AUTH001", "2000-01-01")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["student_id"] == "AUTH001"
        assert data["full_name"] == "Test User"

    def test_successful_login_resets_failed_attempts(self) -> None:
        """After a successful login, failed_attempts resets to 0."""
        self.student.failed_attempts = 3
        self.student.save()

        self._post_login("AUTH001", "2000-01-01")
        self.student.refresh_from_db()
        assert self.student.failed_attempts == 0

    def test_successful_login_creates_audit_record(self) -> None:
        """A successful login creates an audit record with success=True."""
        self._post_login("AUTH001", "2000-01-01")
        log = AuditLog.objects.filter(
            student_id_attempted="AUTH001",
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=True,
        )
        assert log.exists()

    # ---- Failure ----

    def test_wrong_dob_returns_401(self) -> None:
        """Wrong DOB returns 401 with generic error."""
        response = self._post_login("AUTH001", "1999-12-31")
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Invalid credentials" in data["error"]

    def test_nonexistent_student_returns_401(self) -> None:
        """Unknown student_id returns 401 with same generic error."""
        response = self._post_login("NOEXIST", "2000-01-01")
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Invalid credentials" in data["error"]

    def test_failed_login_increments_counter(self) -> None:
        """Each failed login increments failed_attempts."""
        self._post_login("AUTH001", "1999-01-01")
        self.student.refresh_from_db()
        assert self.student.failed_attempts == 1

        self._post_login("AUTH001", "1999-01-01")
        self.student.refresh_from_db()
        assert self.student.failed_attempts == 2

    def test_failed_login_creates_audit_record(self) -> None:
        """A failed login creates an audit record with success=False."""
        self._post_login("AUTH001", "1999-01-01")
        log = AuditLog.objects.filter(
            student_id_attempted="AUTH001",
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
        )
        assert log.exists()

    # ---- Account locking ----

    @override_settings(CEMS_MAX_FAILED_ATTEMPTS=5, CEMS_LOCKOUT_MINUTES=30)
    def test_account_locks_after_threshold(self) -> None:
        """Account locks after CEMS_MAX_FAILED_ATTEMPTS consecutive failures."""
        for i in range(5):
            resp = self._post_login("AUTH001", "1999-01-01")
            assert resp.status_code == 401

        self.student.refresh_from_db()
        assert self.student.failed_attempts >= 5
        assert self.student.is_locked is True
        assert self.student.lock_until is not None

    @override_settings(CEMS_MAX_FAILED_ATTEMPTS=5, CEMS_LOCKOUT_MINUTES=30)
    def test_locked_account_returns_401(self) -> None:
        """Attempting to login to a locked account returns 401."""
        self.student.lock_until = timezone.now() + timedelta(minutes=30)
        self.student.save()

        response = self._post_login("AUTH001", "2000-01-01")
        assert response.status_code == 401
        data = response.json()
        assert "locked" in data["error"].lower()

    def test_lock_expires(self) -> None:
        """After lock_until passes, the account is no longer locked."""
        self.student.lock_until = timezone.now() - timedelta(minutes=1)
        self.student.save()
        assert self.student.is_locked is False

    # ---- Input validation ----

    def test_missing_student_id_returns_400(self) -> None:
        """Missing student_id returns 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({"date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_missing_dob_returns_400(self) -> None:
        """Missing date_of_birth returns 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({"student_id": "AUTH001"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_invalid_dob_format_returns_400(self) -> None:
        """Invalid date format returns 400."""
        response = self._post_login("AUTH001", "01-01-2000")
        assert response.status_code == 400

    def test_get_request_not_allowed(self) -> None:
        """GET is not allowed on the login endpoint."""
        response = self.client.get(self.url)
        assert response.status_code == 405
