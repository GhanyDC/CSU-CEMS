"""
Tests for Bundle 01: Admin Authentication and Role-Based Access.

Covers:
- Admin login/logout via separate auth flow
- Role-based permission enforcement
- Electoral Board Head-only lifecycle protection
- Operator cannot start/close/publish
- Read-only roles cannot mutate
- Student auth cannot access admin endpoints
- Audit logging of admin events
- AdminProfile model behavior
"""
import json
from datetime import date, datetime, timezone

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.audit.models import AuditLog
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from conftest import admin_client_for, create_admin_user, make_eligible, finalize_election_voter_roll


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_election(status=Election.Status.DRAFT):
    return Election.objects.create(
        name="Admin Auth Test Election",
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
    )


def make_student(student_id="STU_ADMIN_TEST", dob="2000-01-01"):
    return Student.objects.create(
        student_id=student_id,
        full_name=f"Student {student_id}",
        date_of_birth=date.fromisoformat(dob),
        course="Test",
        year=1,
    )


# ── Admin Login ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminLogin:
    """Tests for POST /api/admin/auth/login/"""

    def setup_method(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user, self.profile = create_admin_user(
            username="test_admin",
            password="SecurePass123!",
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="Test Admin User",
        )

    def _login(self, username="test_admin", password="SecurePass123!"):
        return self.client.post(
            "/api/admin/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    def test_successful_login(self):
        resp = self._login()
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["username"] == "test_admin"
        assert data["role"] == AdminRole.ELECTORAL_BOARD_HEAD
        assert data["role_display"] == "Electoral Board Head"
        assert data["display_name"] == "Test Admin User"

    def test_wrong_password(self):
        resp = self._login(password="wrongpassword")
        assert resp.status_code == 401
        assert resp.json()["success"] is False

    def test_nonexistent_user(self):
        resp = self._login(username="nobody")
        assert resp.status_code == 401

    def test_missing_fields(self):
        resp = self.client.post(
            "/api/admin/auth/login/",
            data=json.dumps({"username": "test_admin"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_empty_body(self):
        resp = self.client.post(
            "/api/admin/auth/login/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_json(self):
        resp = self.client.post(
            "/api/admin/auth/login/",
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_user_without_admin_profile_rejected(self):
        """A Django User with no AdminProfile cannot log in via admin auth."""
        User.objects.create_user(username="nonadmin", password="Pass1234!")
        resp = self._login(username="nonadmin", password="Pass1234!")
        assert resp.status_code == 401

    def test_inactive_profile_rejected(self):
        """An admin with is_active=False on their profile is rejected."""
        self.profile.is_active = False
        self.profile.save()
        resp = self._login()
        assert resp.status_code == 401

    def test_login_audited_on_success(self):
        self._login()
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_LOGIN_ATTEMPT,
            success=True,
        ).first()
        assert log is not None
        assert log.student_id_attempted == "test_admin"
        assert "successful" in log.details.lower()

    def test_login_audited_on_failure(self):
        self._login(password="wrong")
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_LOGIN_ATTEMPT,
            success=False,
        ).first()
        assert log is not None
        assert log.student_id_attempted == "test_admin"

    def test_get_method_not_allowed(self):
        resp = self.client.get("/api/admin/auth/login/")
        assert resp.status_code == 405

    def test_student_credentials_cannot_admin_login(self):
        """Student ID + birthdate cannot be used at the admin login endpoint."""
        make_student("STU_NO_ADMIN")
        resp = self._login(username="STU_NO_ADMIN", password="2000-01-01")
        assert resp.status_code == 401


# ── Admin Logout ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminLogout:
    """Tests for POST /api/admin/auth/logout/"""

    def test_logout_success(self):
        user, _ = create_admin_user(username="logout_admin")
        client = admin_client_for(user)
        resp = client.post("/api/admin/auth/logout/")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_logout_audited(self):
        user, _ = create_admin_user(username="audit_logout")
        client = admin_client_for(user)
        client.post("/api/admin/auth/logout/")
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_LOGOUT,
            student_id_attempted="audit_logout",
        ).first()
        assert log is not None

    def test_unauthenticated_logout_no_error(self):
        """Logout without being logged in should not error."""
        client = Client(enforce_csrf_checks=False)
        resp = client.post("/api/admin/auth/logout/")
        assert resp.status_code == 200


# ── Auth Separation ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthSeparation:
    """Verify student and admin auth are completely separate."""

    def test_student_session_does_not_grant_admin_access(self):
        """A student logged in via student auth cannot access admin endpoints."""
        student = make_student("SEP001")
        client = Client(enforce_csrf_checks=False)
        client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "SEP001", "date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )
        election = make_election()
        resp = client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_admin_session_does_not_grant_student_access(self):
        """An admin logged in via Django auth cannot access student endpoints."""
        user, _ = create_admin_user(username="admin_no_student")
        client = admin_client_for(user)
        resp = client.get("/api/elections/current/")
        # Student endpoints check authenticated_student_id in session, not request.user
        assert resp.status_code == 401

    def test_student_with_is_admin_flag_cannot_use_admin_endpoints(self):
        """Even a student with is_admin=True cannot access new admin auth endpoints."""
        student = Student.objects.create(
            student_id="OLD_ADMIN",
            full_name="Old Admin",
            date_of_birth=date(2000, 1, 1),
            course="Test",
            year=1,
            is_admin=True,
        )
        client = Client(enforce_csrf_checks=False)
        session = client.session
        session["authenticated_student_id"] = str(student.pk)
        session.save()

        election = make_election()
        resp = client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 401


# ── Role-Based Permission Enforcement ────────────────────────────────────────

@pytest.mark.django_db
class TestRolePermissions:
    """Test that each role has the correct access level."""

    def setup_method(self):
        self.eb_head_user, _ = create_admin_user(
            username="head",
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="EB Head",
        )
        self.operator_user, _ = create_admin_user(
            username="operator",
            role=AdminRole.ELECTORAL_BOARD_OPERATOR,
            display_name="Operator",
        )
        self.tally_watcher_user, _ = create_admin_user(
            username="tally",
            role=AdminRole.TALLY_WATCHER,
            display_name="Tally Watcher",
        )
        self.auditor_user, _ = create_admin_user(
            username="auditor",
            role=AdminRole.AUDITOR,
            display_name="Auditor",
        )
        self.tech_support_user, _ = create_admin_user(
            username="techsup",
            role=AdminRole.TECHNICAL_SUPPORT,
            display_name="Tech Support",
        )

    def _start(self, user, election_id):
        client = admin_client_for(user)
        return client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    def _close(self, user, election_id):
        client = admin_client_for(user)
        return client.post(
            "/api/admin/elections/close/",
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    def _publish(self, user, election_id):
        client = admin_client_for(user)
        return client.post(
            "/api/admin/elections/publish/",
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    # ── Electoral Board Head ──

    def test_eb_head_can_start(self):
        election = make_election(status=Election.Status.DRAFT)
        s = Student.objects.create(
            student_id="VRSETUP01", full_name="VR Setup",
            date_of_birth=date(2001, 1, 1), course="Test", year=1,
        )
        make_eligible(s, election)
        finalize_election_voter_roll(election)
        resp = self._start(self.eb_head_user, election.pk)
        assert resp.status_code == 200

    def test_eb_head_can_close(self):
        election = make_election(status=Election.Status.ACTIVE)
        resp = self._close(self.eb_head_user, election.pk)
        assert resp.status_code == 200

    def test_eb_head_can_publish(self):
        election = make_election(status=Election.Status.CLOSED)
        resp = self._publish(self.eb_head_user, election.pk)
        assert resp.status_code == 200

    # ── Electoral Board Operator (cannot start/close/publish) ──

    def test_operator_cannot_start(self):
        election = make_election(status=Election.Status.DRAFT)
        resp = self._start(self.operator_user, election.pk)
        assert resp.status_code == 403

    def test_operator_cannot_close(self):
        election = make_election(status=Election.Status.ACTIVE)
        resp = self._close(self.operator_user, election.pk)
        assert resp.status_code == 403

    def test_operator_cannot_publish(self):
        election = make_election(status=Election.Status.CLOSED)
        resp = self._publish(self.operator_user, election.pk)
        assert resp.status_code == 403

    # ── Tally Watcher (read-only, cannot start/close/publish) ──

    def test_tally_watcher_cannot_start(self):
        election = make_election(status=Election.Status.DRAFT)
        resp = self._start(self.tally_watcher_user, election.pk)
        assert resp.status_code == 403

    def test_tally_watcher_cannot_close(self):
        election = make_election(status=Election.Status.ACTIVE)
        resp = self._close(self.tally_watcher_user, election.pk)
        assert resp.status_code == 403

    def test_tally_watcher_cannot_publish(self):
        election = make_election(status=Election.Status.CLOSED)
        resp = self._publish(self.tally_watcher_user, election.pk)
        assert resp.status_code == 403

    # ── Auditor (read-only, cannot start/close/publish) ──

    def test_auditor_cannot_start(self):
        election = make_election(status=Election.Status.DRAFT)
        resp = self._start(self.auditor_user, election.pk)
        assert resp.status_code == 403

    def test_auditor_cannot_close(self):
        election = make_election(status=Election.Status.ACTIVE)
        resp = self._close(self.auditor_user, election.pk)
        assert resp.status_code == 403

    def test_auditor_cannot_publish(self):
        election = make_election(status=Election.Status.CLOSED)
        resp = self._publish(self.auditor_user, election.pk)
        assert resp.status_code == 403

    # ── Technical Support (no election-authority actions) ──

    def test_tech_support_cannot_start(self):
        election = make_election(status=Election.Status.DRAFT)
        resp = self._start(self.tech_support_user, election.pk)
        assert resp.status_code == 403

    def test_tech_support_cannot_close(self):
        election = make_election(status=Election.Status.ACTIVE)
        resp = self._close(self.tech_support_user, election.pk)
        assert resp.status_code == 403

    def test_tech_support_cannot_publish(self):
        election = make_election(status=Election.Status.CLOSED)
        resp = self._publish(self.tech_support_user, election.pk)
        assert resp.status_code == 403


# ── Permission Denied Audit Logging ──────────────────────────────────────────

@pytest.mark.django_db
class TestPermissionDeniedAudit:
    """Verify that permission-denied attempts are logged."""

    def test_operator_denied_action_is_audited(self):
        user, _ = create_admin_user(
            username="audit_op",
            role=AdminRole.ELECTORAL_BOARD_OPERATOR,
            display_name="Audit Op",
        )
        election = make_election(status=Election.Status.DRAFT)
        client = admin_client_for(user)
        client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_PERMISSION_DENIED,
            student_id_attempted="audit_op",
        ).first()
        assert log is not None
        assert "electoral_board_operator" in log.details.lower()

    def test_tally_watcher_denied_action_is_audited(self):
        user, _ = create_admin_user(
            username="audit_tw",
            role=AdminRole.TALLY_WATCHER,
            display_name="Audit TW",
        )
        election = make_election(status=Election.Status.ACTIVE)
        client = admin_client_for(user)
        client.post(
            "/api/admin/elections/close/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_PERMISSION_DENIED,
            student_id_attempted="audit_tw",
        ).first()
        assert log is not None


# ── AdminProfile Model Tests ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminProfileModel:
    """Tests for AdminProfile model properties."""

    def test_is_electoral_board_head(self):
        _, profile = create_admin_user(role=AdminRole.ELECTORAL_BOARD_HEAD)
        assert profile.is_electoral_board_head is True
        assert profile.is_operator is False
        assert profile.is_read_only is False

    def test_is_operator(self):
        _, profile = create_admin_user(
            username="op",
            role=AdminRole.ELECTORAL_BOARD_OPERATOR,
            display_name="Op",
        )
        assert profile.is_electoral_board_head is False
        assert profile.is_operator is True
        assert profile.is_read_only is False

    def test_tally_watcher_is_read_only(self):
        _, profile = create_admin_user(
            username="tw",
            role=AdminRole.TALLY_WATCHER,
            display_name="TW",
        )
        assert profile.is_read_only is True

    def test_auditor_is_read_only(self):
        _, profile = create_admin_user(
            username="aud",
            role=AdminRole.AUDITOR,
            display_name="Aud",
        )
        assert profile.is_read_only is True

    def test_tech_support_is_read_only(self):
        _, profile = create_admin_user(
            username="ts",
            role=AdminRole.TECHNICAL_SUPPORT,
            display_name="TS",
        )
        assert profile.is_read_only is True

    def test_str_representation(self):
        _, profile = create_admin_user(
            username="str_test",
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="VP Str Test",
        )
        assert "VP Str Test" in str(profile)
        assert "Electoral Board Head" in str(profile)

    def test_admin_role_choices(self):
        """All required roles exist in AdminRole."""
        role_values = [r.value for r in AdminRole]
        assert "electoral_board_head" in role_values
        assert "electoral_board_operator" in role_values
        assert "tally_watcher" in role_values
        assert "auditor" in role_values
        assert "technical_support" in role_values
