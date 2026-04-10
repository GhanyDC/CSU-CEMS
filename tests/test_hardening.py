"""
Tests for Full Hardening & Bug-Fix Run 01.

Covers:
- Admin login template block fix regression
- CSRF token presence in login forms
- Session isolation between admin and student auth
- Logout CSRF protection
- Anonymous page rendering (no errors on anonymous pages)
- Role escalation prevention (operator → EB Head actions)
- Tally/Auditor/Tech Support cannot mutate
- Student cannot access admin endpoints
- Admin credentials cannot work via student login
- Cross-college election isolation
- Unapproved voter blocked from voting
- Direct API tampering with election/candidate/position IDs
- Duplicate ballot submission prevented
- Tally blocked during Active status
- Results blocked before Publish
- Route collision checks
- Redirect loop checks
"""
import json
from datetime import date, datetime, timezone

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.audit.models import AuditLog
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import Candidate, Election, EligibleVoter, Position, VerificationRecord
from apps.voting.models import Ballot, BallotSelection
from conftest import (
    admin_client_for,
    create_admin_user,
    finalize_election_voter_roll,
    make_eligible,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_election(status=Election.Status.DRAFT, **kwargs):
    defaults = dict(
        name="Hardening Test Election",
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
    )
    defaults.update(kwargs)
    return Election.objects.create(**defaults)


def _make_college_election(college, status=Election.Status.DRAFT, **kwargs):
    return _make_election(
        name=f"College Election – {college}",
        election_type=Election.ElectionType.COLLEGE,
        college=college,
        status=status,
        **kwargs,
    )


def _make_student(student_id="STU_H001", college="College of Nursing", dob="2000-03-15"):
    return Student.objects.create(
        student_id=student_id,
        full_name=f"Student {student_id}",
        date_of_birth=date.fromisoformat(dob),
        college=college,
        course="Test Course",
        year=2,
    )


def _student_login(client, student):
    """Login a student via API and return the response."""
    return client.post(
        "/api/auth/login/",
        data=json.dumps({
            "student_id": student.student_id,
            "date_of_birth": student.date_of_birth.isoformat(),
        }),
        content_type="application/json",
    )


def _admin_login(client, username="eb_head", password="securePass123!"):
    """Login an admin via API and return the response."""
    return client.post(
        "/api/admin/auth/login/",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )


def _setup_votable_election(student, election=None):
    """Create an Active election with a position, candidate, and eligible voter."""
    if election is None:
        election = _make_election(status=Election.Status.ACTIVE)
    pos = Position.objects.create(
        election=election,
        title="President",
        category=Position.Category.EXECUTIVE,
        max_selections=1,
        order=1,
    )
    cand = Candidate.objects.create(
        position=pos, full_name="Test Candidate", party="Test Party",
    )
    make_eligible(student, election)
    return election, pos, cand


# ═══════════════════════════════════════════════════════════════════════════
# 1. Admin Login Template Fix Regression
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAdminLoginTemplateRegression:
    """Verify the admin login page renders correctly with JS block."""

    def test_admin_login_page_returns_200(self):
        resp = Client().get("/election-admin/login/")
        assert resp.status_code == 200

    def test_admin_login_page_contains_js_form_handler(self):
        """The JS form handler must be rendered (block extra_scripts, not extra_js)."""
        resp = Client().get("/election-admin/login/")
        content = resp.content.decode()
        assert "admin-login-form" in content
        assert "/api/admin/auth/login/" in content
        assert "addEventListener" in content
        assert "fetch(" in content  # The JS must include the fetch call

    def test_admin_login_page_contains_csrf_hidden_field(self):
        """The form must include a CSRF hidden field for production compatibility."""
        resp = Client().get("/election-admin/login/")
        content = resp.content.decode()
        assert 'csrfmiddlewaretoken' in content

    def test_student_login_page_contains_csrf_hidden_field(self):
        """The student login form must also include a CSRF hidden field."""
        resp = Client().get("/")
        content = resp.content.decode()
        assert 'csrfmiddlewaretoken' in content

    def test_admin_login_redirect_when_authenticated(self):
        """Already-authenticated admin should be redirected to admin-panel."""
        user, _ = create_admin_user()
        client = Client()
        client.force_login(user)
        resp = client.get("/election-admin/login/")
        assert resp.status_code == 302
        assert "/admin-panel/" in resp.url


# ═══════════════════════════════════════════════════════════════════════════
# 2. Session Isolation Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSessionIsolation:
    """Verify admin and student sessions do not cross-contaminate."""

    def test_admin_login_clears_student_session(self):
        """Admin login should clear any lingering student session keys."""
        client = Client(enforce_csrf_checks=False)
        student = _make_student()

        # Login as student first
        resp = _student_login(client, student)
        assert resp.json()["success"] is True
        assert client.session.get("authenticated_student_id") is not None

        # Now login as admin
        user, _ = create_admin_user(password="TestPass1!")
        resp = _admin_login(client, username="eb_head", password="TestPass1!")
        assert resp.json()["success"] is True

        # Student session keys should be cleared
        assert client.session.get("authenticated_student_id") is None
        assert client.session.get("student_id") is None

    def test_student_login_clears_admin_session(self):
        """Student login should clear any lingering Django auth session."""
        client = Client(enforce_csrf_checks=False)
        student = _make_student()

        # Login as admin first
        user, _ = create_admin_user(password="TestPass2!")
        resp = _admin_login(client, username="eb_head", password="TestPass2!")
        assert resp.json()["success"] is True

        # Now login as student
        resp = _student_login(client, student)
        assert resp.json()["success"] is True

        # Admin endpoints should reject (Django auth cleared)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 401

    def test_student_credentials_cannot_access_admin_endpoints(self):
        """A student session must not grant access to admin API endpoints."""
        client = Client(enforce_csrf_checks=False)
        student = _make_student()
        _student_login(client, student)

        admin_endpoints = [
            "/api/admin/elections/setup/list/",
        ]
        for url in admin_endpoints:
            resp = client.get(url)
            assert resp.status_code == 401, f"Expected 401 for {url}, got {resp.status_code}"

    def test_admin_session_cannot_access_student_endpoints(self):
        """An admin Django auth session without student session should be rejected from student endpoints."""
        user, _ = create_admin_user(password="TestPass3!")
        client = Client(enforce_csrf_checks=False)
        _admin_login(client, username="eb_head", password="TestPass3!")

        student_endpoints = [
            "/api/elections/mine/",
            "/api/elections/status/",
        ]
        for url in student_endpoints:
            resp = client.get(url)
            assert resp.status_code == 401, f"Expected 401 for {url}, got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Anonymous Page Rendering Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAnonymousPageRendering:
    """All anonymous-accessible pages must render without errors."""

    def test_student_login_page(self):
        resp = Client().get("/")
        assert resp.status_code == 200
        assert b"CEMS" in resp.content

    def test_admin_login_page(self):
        resp = Client().get("/election-admin/login/")
        assert resp.status_code == 200
        assert b"CEMS Admin" in resp.content

    def test_dashboard_redirects_anonymous(self):
        resp = Client().get("/dashboard/")
        assert resp.status_code == 302

    def test_ballot_redirects_anonymous(self):
        resp = Client().get("/ballot/")
        assert resp.status_code == 302

    def test_results_redirects_anonymous(self):
        resp = Client().get("/results/")
        assert resp.status_code == 302

    def test_admin_panel_redirects_anonymous(self):
        resp = Client().get("/admin-panel/")
        assert resp.status_code == 302
        assert "election-admin/login" in resp.url

    def test_django_admin_is_separate(self):
        """Django's built-in admin must still be accessible at /admin/."""
        resp = Client().get("/admin/login/")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 4. Role Escalation Prevention
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRoleEscalation:
    """Admins with lower privileges must not access higher-privilege actions."""

    def setup_method(self):
        self.election = _make_election(status=Election.Status.DRAFT)
        finalize_election_voter_roll(self.election)
        self.student = _make_student()
        make_eligible(self.student, self.election)

    def _lifecycle_post(self, client, action, election_id):
        return client.post(
            f"/api/admin/elections/{action}/",
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    def test_operator_cannot_start_election(self):
        user, _ = create_admin_user(
            username="op_esc", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        client = admin_client_for(user)
        resp = self._lifecycle_post(client, "start", self.election.pk)
        assert resp.status_code == 403

    def test_operator_cannot_close_election(self):
        self.election.status = Election.Status.ACTIVE
        self.election.save()
        user, _ = create_admin_user(
            username="op_close", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        client = admin_client_for(user)
        resp = self._lifecycle_post(client, "close", self.election.pk)
        assert resp.status_code == 403

    def test_operator_cannot_publish_results(self):
        self.election.status = Election.Status.CLOSED
        self.election.save()
        user, _ = create_admin_user(
            username="op_pub", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        client = admin_client_for(user)
        resp = self._lifecycle_post(client, "publish", self.election.pk)
        assert resp.status_code == 403

    def test_tally_watcher_cannot_start_election(self):
        user, _ = create_admin_user(
            username="tw_start", role=AdminRole.TALLY_WATCHER
        )
        client = admin_client_for(user)
        resp = self._lifecycle_post(client, "start", self.election.pk)
        assert resp.status_code == 403

    def test_auditor_cannot_modify_candidates(self):
        user, _ = create_admin_user(
            username="aud_mod", role=AdminRole.AUDITOR
        )
        client = admin_client_for(user)
        resp = client.post(
            f"/api/admin/elections/setup/{self.election.pk}/candidates/add/",
            data=json.dumps({"position_id": "fake", "full_name": "Fake"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_finalize_voter_roll(self):
        user, _ = create_admin_user(
            username="op_fin", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        client = admin_client_for(user)
        resp = client.post(
            f"/api/admin/elections/setup/{self.election.pk}/voter-roll/finalize/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_technical_support_cannot_access_any_setup_endpoint(self):
        user, _ = create_admin_user(
            username="tech_esc", role=AdminRole.TECHNICAL_SUPPORT
        )
        client = admin_client_for(user)
        endpoints = [
            f"/api/admin/elections/setup/list/",
            f"/api/admin/elections/setup/{self.election.pk}/",
            f"/api/admin/elections/{self.election.pk}/turnout/",
            f"/api/admin/elections/{self.election.pk}/tally/",
        ]
        for url in endpoints:
            resp = client.get(url)
            assert resp.status_code == 403, f"Expected 403 for tech support on {url}"

    def test_permission_denied_is_audit_logged(self):
        """Permission-denied events should appear in the audit log."""
        user, _ = create_admin_user(
            username="aud_log_test", role=AdminRole.TALLY_WATCHER
        )
        client = admin_client_for(user)
        client.post(
            f"/api/admin/elections/setup/{self.election.pk}/candidates/add/",
            data=json.dumps({"position_id": "fake", "full_name": "Fake"}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.ADMIN_PERMISSION_DENIED,
            student_id_attempted="aud_log_test",
        ).exists()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Cross-College Election Isolation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCrossColegeIsolation:
    """Students must not see or vote in elections for other colleges."""

    def setup_method(self):
        self.nursing_student = _make_student(
            student_id="NURSE001", college="College of Nursing"
        )
        self.eng_student = _make_student(
            student_id="ENG001", college="College of Architecture and Engineering"
        )
        self.nursing_election = _make_college_election(
            "College of Nursing", status=Election.Status.ACTIVE
        )
        self.eng_election = _make_college_election(
            "College of Architecture and Engineering", status=Election.Status.ACTIVE
        )

        # Both students are on their own college voter rolls
        make_eligible(self.nursing_student, self.nursing_election)
        make_eligible(self.eng_student, self.eng_election)

        # Set up positions and candidates
        for election in [self.nursing_election, self.eng_election]:
            pos = Position.objects.create(
                election=election, title="Governor",
                category=Position.Category.COLLEGE_EXECUTIVE,
                max_selections=1, order=1,
            )
            Candidate.objects.create(
                position=pos, full_name=f"Gov Candidate ({election.college})",
            )

    def test_nursing_student_cannot_see_engineering_ballot(self):
        client = Client(enforce_csrf_checks=False)
        _student_login(client, self.nursing_student)
        resp = client.get(f"/api/elections/{self.eng_election.pk}/ballot/")
        assert resp.status_code == 403

    def test_engineering_student_cannot_see_nursing_ballot(self):
        client = Client(enforce_csrf_checks=False)
        _student_login(client, self.eng_student)
        resp = client.get(f"/api/elections/{self.nursing_election.pk}/ballot/")
        assert resp.status_code == 403

    def test_nursing_student_cannot_vote_in_engineering_election(self):
        client = Client(enforce_csrf_checks=False)
        _student_login(client, self.nursing_student)
        eng_pos = Position.objects.filter(election=self.eng_election).first()
        eng_cand = Candidate.objects.filter(position=eng_pos).first()
        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(self.eng_election.pk),
                "selections": [
                    {"position_id": str(eng_pos.pk), "candidate_id": str(eng_cand.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_my_elections_only_shows_own_college(self):
        client = Client(enforce_csrf_checks=False)
        _student_login(client, self.nursing_student)
        resp = client.get("/api/elections/mine/")
        data = resp.json()
        assert data["success"] is True
        election_ids = [e["id"] for e in data["elections"]]
        assert str(self.nursing_election.pk) in election_ids
        assert str(self.eng_election.pk) not in election_ids


# ═══════════════════════════════════════════════════════════════════════════
# 6. Unapproved Voter Access Prevention
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUnapprovedVoterAccess:
    """Students NOT on the voter roll cannot vote or see ballot."""

    def test_unapproved_student_cannot_view_ballot(self):
        student = _make_student(student_id="UNAPPROVED1")
        election = _make_election(status=Election.Status.ACTIVE)
        Position.objects.create(
            election=election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )
        # Student is NOT made eligible

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 403

    def test_unapproved_student_cannot_cast_ballot(self):
        student = _make_student(student_id="UNAPPROVED2")
        election = _make_election(status=Election.Status.ACTIVE)
        pos = Position.objects.create(
            election=election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )
        cand = Candidate.objects.create(position=pos, full_name="Candidate A")
        # Student is NOT made eligible

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 7. Direct API Tampering
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAPITampering:
    """Test that bad/forged IDs in API calls fail cleanly."""

    def setup_method(self):
        self.student = _make_student(student_id="TAMPER001")
        self.election, self.pos, self.cand = _setup_votable_election(self.student)
        self.client = Client(enforce_csrf_checks=False)
        _student_login(self.client, self.student)

    def test_cast_ballot_with_wrong_election_id(self):
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": "00000000-0000-0000-0000-000000000000",
                "selections": [
                    {"position_id": str(self.pos.pk), "candidate_id": str(self.cand.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_cast_ballot_with_invalid_uuid(self):
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": "not-a-uuid",
                "selections": [
                    {"position_id": str(self.pos.pk), "candidate_id": str(self.cand.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cast_ballot_with_wrong_position_id(self):
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(self.election.pk),
                "selections": [
                    {"position_id": "00000000-0000-0000-0000-000000000000", "candidate_id": str(self.cand.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cast_ballot_with_wrong_candidate_id(self):
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(self.election.pk),
                "selections": [
                    {"position_id": str(self.pos.pk), "candidate_id": "00000000-0000-0000-0000-000000000000"},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cast_ballot_exceeding_max_selections(self):
        """Cannot select more candidates than max_selections for a position."""
        cand2 = Candidate.objects.create(
            position=self.pos, full_name="Second Candidate",
        )
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(self.election.pk),
                "selections": [
                    {"position_id": str(self.pos.pk), "candidate_id": str(self.cand.pk)},
                    {"position_id": str(self.pos.pk), "candidate_id": str(cand2.pk)},
                ],
            }),
            content_type="application/json",
        )
        # max_selections for President is 1, sending 2 should fail
        assert resp.status_code == 400

    def test_cast_ballot_with_inactive_candidate(self):
        """Cannot vote for an inactive candidate."""
        self.cand.is_active = False
        self.cand.save()
        resp = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(self.election.pk),
                "selections": [
                    {"position_id": str(self.pos.pk), "candidate_id": str(self.cand.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_admin_setup_with_wrong_election_id(self):
        """Admin endpoints should return 404 for non-existent elections."""
        user, _ = create_admin_user(username="admin_tamper")
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/00000000-0000-0000-0000-000000000000/")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 8. Duplicate Ballot Prevention
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDuplicateBallotPrevention:
    """Duplicate ballot submission must be blocked."""

    def test_duplicate_ballot_returns_409(self):
        student = _make_student(student_id="DUP001")
        election, pos, cand = _setup_votable_election(student)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)

        ballot_data = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })

        # First ballot succeeds
        resp = client.post("/api/voting/cast/", data=ballot_data, content_type="application/json")
        assert resp.status_code == 201

        # Second ballot must fail
        resp = client.post("/api/voting/cast/", data=ballot_data, content_type="application/json")
        assert resp.status_code == 409

    def test_duplicate_attempt_is_audit_logged(self):
        student = _make_student(student_id="DUP_AUDIT")
        election, pos, cand = _setup_votable_election(student)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)

        ballot_data = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })

        client.post("/api/voting/cast/", data=ballot_data, content_type="application/json")
        client.post("/api/voting/cast/", data=ballot_data, content_type="application/json")

        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.SUSPICIOUS_ACTIVITY,
            student_id_attempted="DUP_AUDIT",
        ).exists()


# ═══════════════════════════════════════════════════════════════════════════
# 9. Tally Blocking During Active & Results Before Publish
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestVisibilityControls:
    """Enforce tally/result visibility rules per election status."""

    def setup_method(self):
        self.user, _ = create_admin_user(username="vis_admin")
        self.admin_client = admin_client_for(self.user)

    def test_tally_blocked_during_active(self):
        """EB Head CAN see tally during Active; non-EB-Head roles cannot."""
        election = _make_election(status=Election.Status.ACTIVE)
        # EB Head can see live tally during Active
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200

    def test_tally_blocked_during_active_for_operator(self):
        """Operator cannot see live tally during Active."""
        from apps.accounts.models import AdminRole
        op_user, _ = create_admin_user(
            username="vis_operator", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        op_client = admin_client_for(op_user)
        election = _make_election(status=Election.Status.ACTIVE)
        resp = op_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 403

    def test_tally_blocked_during_active_for_tally_watcher(self):
        """Tally Watcher cannot see live tally during Active."""
        from apps.accounts.models import AdminRole
        tw_user, _ = create_admin_user(
            username="vis_tw", role=AdminRole.TALLY_WATCHER
        )
        tw_client = admin_client_for(tw_user)
        election = _make_election(status=Election.Status.ACTIVE)
        resp = tw_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 403

    def test_tally_blocked_during_draft(self):
        election = _make_election(status=Election.Status.DRAFT)
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 403

    def test_tally_available_after_close(self):
        election = _make_election(status=Election.Status.CLOSED)
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200

    def test_tally_available_after_publish(self):
        election = _make_election(status=Election.Status.PUBLISHED)
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200

    def test_turnout_blocked_during_draft(self):
        election = _make_election(status=Election.Status.DRAFT)
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert resp.status_code == 403

    def test_turnout_available_during_active(self):
        election = _make_election(status=Election.Status.ACTIVE)
        resp = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert resp.status_code == 200

    def test_student_results_blocked_before_publish(self):
        student = _make_student(student_id="VIS001")
        election = _make_election(status=Election.Status.CLOSED)
        make_eligible(student, election)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 403

    def test_student_results_available_after_publish(self):
        student = _make_student(student_id="VIS002")
        election = _make_election(status=Election.Status.PUBLISHED)
        make_eligible(student, election)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 10. Route Collision & Redirect Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRouteCollisions:
    """Ensure no route collisions or redirect loops."""

    def test_no_redirect_loop_on_student_login(self):
        """Unauthenticated GET to / must return 200 (login page), not a redirect loop."""
        resp = Client().get("/", follow=True)
        assert resp.status_code == 200
        # Should not have more than 0 redirects
        assert len(resp.redirect_chain) == 0

    def test_no_redirect_loop_on_admin_login(self):
        resp = Client().get("/election-admin/login/", follow=True)
        assert resp.status_code == 200
        assert len(resp.redirect_chain) == 0

    def test_authenticated_student_login_redirects_to_dashboard(self):
        client = Client(enforce_csrf_checks=False)
        student = _make_student(student_id="REDIR001")
        _student_login(client, student)
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/dashboard/" in resp.url

    def test_election_admin_path_distinct_from_django_admin(self):
        """election-admin/login/ must NOT return Django admin content."""
        resp = Client().get("/election-admin/login/")
        content = resp.content.decode()
        assert "CEMS Admin" in content
        # Django admin login has "Django administration" text
        assert "Django administration" not in content

    def test_django_admin_path_distinct(self):
        """Django admin must NOT return CEMS election admin content."""
        resp = Client().get("/admin/login/?next=/admin/")
        content = resp.content.decode()
        assert "Django" in content or "administration" in content.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 11. Election Lifecycle Integrity
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestElectionLifecycleIntegrity:
    """Verify lifecycle transitions enforce proper ordering and gate checks."""

    def setup_method(self):
        self.user, _ = create_admin_user(username="lc_admin")
        self.client = admin_client_for(self.user)

    def _lifecycle_post(self, action, election_id):
        return self.client.post(
            f"/api/admin/elections/{action}/",
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    def test_cannot_start_without_finalized_voter_roll(self):
        election = _make_election(status=Election.Status.DRAFT)
        student = _make_student(student_id="LC001")
        make_eligible(student, election)
        # Voter roll NOT finalized
        resp = self._lifecycle_post("start", election.pk)
        assert resp.status_code == 409
        assert "voter roll" in resp.json()["error"].lower()

    def test_cannot_close_draft_election(self):
        election = _make_election(status=Election.Status.DRAFT)
        resp = self._lifecycle_post("close", election.pk)
        assert resp.status_code == 409

    def test_cannot_publish_active_election(self):
        election = _make_election(status=Election.Status.ACTIVE)
        resp = self._lifecycle_post("publish", election.pk)
        assert resp.status_code == 409

    def test_cannot_start_closed_election(self):
        election = _make_election(status=Election.Status.CLOSED)
        resp = self._lifecycle_post("start", election.pk)
        assert resp.status_code == 409

    def test_cannot_perform_actions_on_published_election(self):
        election = _make_election(status=Election.Status.PUBLISHED)
        for action in ["start", "close", "publish"]:
            resp = self._lifecycle_post(action, election.pk)
            assert resp.status_code == 409, f"Expected 409 for {action} on published"


# ═══════════════════════════════════════════════════════════════════════════
# 12. Auth Flow End-to-End
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAuthFlowEndToEnd:
    """Full auth roundtrip tests for both admin and student."""

    def test_admin_login_then_access_panel(self):
        """Admin login via API → access admin panel → logout."""
        user, _ = create_admin_user(username="e2e_admin", password="TestE2E!")
        client = Client(enforce_csrf_checks=False)

        # Login
        resp = _admin_login(client, username="e2e_admin", password="TestE2E!")
        assert resp.json()["success"] is True

        # Access admin panel
        resp = client.get("/admin-panel/")
        assert resp.status_code == 200

        # Access API
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 200

        # Logout
        resp = client.post("/api/admin/auth/logout/")
        assert resp.json()["success"] is True

        # API should be blocked
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 401

    def test_student_login_then_access_dashboard(self):
        """Student login via API → access dashboard → logout."""
        student = _make_student(student_id="E2E_STU")
        client = Client(enforce_csrf_checks=False)

        # Login
        resp = _student_login(client, student)
        assert resp.json()["success"] is True

        # Access dashboard page
        resp = client.get("/dashboard/")
        assert resp.status_code == 200

        # Access API
        resp = client.get("/api/elections/mine/")
        assert resp.status_code == 200

        # Logout
        resp = client.post("/api/auth/logout/")
        assert resp.json()["success"] is True

        # API should be blocked
        resp = client.get("/api/elections/mine/")
        assert resp.status_code == 401

    def test_wrong_student_credentials_fail(self):
        student = _make_student(student_id="WRONG001", dob="2001-06-15")
        client = Client(enforce_csrf_checks=False)
        resp = client.post(
            "/api/auth/login/",
            data=json.dumps({
                "student_id": "WRONG001",
                "date_of_birth": "1999-01-01",  # Wrong DOB
            }),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_wrong_admin_credentials_fail(self):
        create_admin_user(username="bad_admin", password="GoodPass1!")
        client = Client(enforce_csrf_checks=False)
        resp = _admin_login(client, username="bad_admin", password="WrongPass!")
        assert resp.status_code == 401

    def test_admin_credentials_fail_on_student_login(self):
        """Admin username+password must not work via student login endpoint."""
        create_admin_user(username="cross_admin", password="CrossTest1!")
        client = Client(enforce_csrf_checks=False)
        resp = client.post(
            "/api/auth/login/",
            data=json.dumps({
                "student_id": "cross_admin",
                "date_of_birth": "2000-01-01",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_nonexistent_admin_returns_401(self):
        client = Client(enforce_csrf_checks=False)
        resp = _admin_login(client, username="ghost_admin", password="anything")
        assert resp.status_code == 401

    def test_inactive_admin_profile_blocked(self):
        """Admin user with inactive profile must not authenticate."""
        user, profile = create_admin_user(username="inactive_admin", password="Pass1!")
        profile.is_active = False
        profile.save()
        client = Client(enforce_csrf_checks=False)
        resp = _admin_login(client, username="inactive_admin", password="Pass1!")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 13. Voting During Non-Active Election
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestVotingNonActive:
    """Voting must only work during ACTIVE status."""

    def test_cannot_vote_in_draft_election(self):
        student = _make_student(student_id="DRAFT_V")
        election = _make_election(status=Election.Status.DRAFT)
        pos = Position.objects.create(
            election=election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )
        cand = Candidate.objects.create(position=pos, full_name="Draft Candidate")
        make_eligible(student, election)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_cannot_vote_in_closed_election(self):
        student = _make_student(student_id="CLOSED_V")
        election = _make_election(status=Election.Status.CLOSED)
        pos = Position.objects.create(
            election=election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )
        cand = Candidate.objects.create(position=pos, full_name="Closed Candidate")
        make_eligible(student, election)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_cannot_vote_in_published_election(self):
        student = _make_student(student_id="PUB_V")
        election = _make_election(status=Election.Status.PUBLISHED)
        pos = Position.objects.create(
            election=election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )
        cand = Candidate.objects.create(position=pos, full_name="Pub Candidate")
        make_eligible(student, election)

        client = Client(enforce_csrf_checks=False)
        _student_login(client, student)
        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 409
