"""
Tests for HTTP-level view endpoints.

Covers:
- Election endpoints (current, status, results)
- Voting endpoint (cast ballot)
- Admin lifecycle endpoints (start, close, publish)
- Authentication/authorization checks on all endpoints
"""
import json
from datetime import date, datetime, timezone

import pytest
from django.test import Client
from django.utils import timezone as tz

from apps.accounts.models import AdminRole, Student
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.voting.models import Ballot
from conftest import admin_client_for, create_admin_user, make_eligible, finalize_election_voter_roll


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_student(student_id="VIEW001", full_name="View Test User", is_admin=False):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        date_of_birth=date(2001, 1, 1),
        course="Test",
        year=1,
        is_admin=is_admin,
    )


def make_election(name="Test Election", status=Election.Status.ACTIVE):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
    )


def make_position(election, title="President", category="executive", max_selections=1, order=0):
    return Position.objects.create(
        election=election, title=title, category=category,
        max_selections=max_selections, order=order,
    )


def make_candidate(position, full_name="Candidate A", party="Party X"):
    return Candidate.objects.create(
        position=position, full_name=full_name, party=party,
    )


def auth_client(student):
    """Return a test client authenticated as the given student."""
    client = Client(enforce_csrf_checks=False)
    session = client.session
    session["authenticated_student_id"] = str(student.pk)
    session.save()
    return client


def unauth_client():
    """Return an unauthenticated test client."""
    return Client(enforce_csrf_checks=False)


# ── Current Election ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCurrentElectionView:
    """Tests for GET /api/elections/current/"""

    def test_unauthenticated_returns_401(self):
        response = unauth_client().get("/api/elections/current/")
        assert response.status_code == 401

    def test_no_active_election_returns_404(self):
        student = make_student()
        client = auth_client(student)
        response = client.get("/api/elections/current/")
        assert response.status_code == 404
        assert response.json()["error"] == "No active election at this time."

    def test_returns_active_election_with_positions(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get("/api/elections/current/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["election"]["name"] == "Test Election"
        assert len(data["election"]["positions"]) == 1
        assert len(data["election"]["positions"][0]["candidates"]) == 1
        assert data["election"]["positions"][0]["candidates"][0]["full_name"] == "Candidate A"

    def test_inactive_candidates_excluded(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        make_candidate(pos, full_name="Active")
        inactive = make_candidate(pos, full_name="Inactive")
        inactive.is_active = False
        inactive.save()
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get("/api/elections/current/")
        candidates = response.json()["election"]["positions"][0]["candidates"]
        names = [c["full_name"] for c in candidates]
        assert "Active" in names
        assert "Inactive" not in names

    def test_post_not_allowed(self):
        student = make_student()
        client = auth_client(student)
        response = client.post("/api/elections/current/")
        assert response.status_code == 405


# ── Voting Status ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVotingStatusView:
    """Tests for GET /api/elections/status/"""

    def test_unauthenticated_returns_401(self):
        response = unauth_client().get("/api/elections/status/")
        assert response.status_code == 401

    def test_no_active_election(self):
        student = make_student()
        client = auth_client(student)
        response = client.get("/api/elections/status/")
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_election"] is False

    def test_has_not_voted(self):
        student = make_student()
        election = make_election()
        make_eligible(student, election)
        client = auth_client(student)
        response = client.get("/api/elections/status/")
        data = response.json()
        assert data["has_active_election"] is True
        assert data["has_voted"] is False

    def test_has_voted(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)
        make_eligible(student, election)
        # Create a ballot for this student
        hashed = Ballot.hash_student_id(student.student_id, str(election.pk))
        Ballot.objects.create(election=election, hashed_student_id=hashed)

        client = auth_client(student)
        response = client.get("/api/elections/status/")
        data = response.json()
        assert data["has_voted"] is True


# ── Election Results ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionResultsView:
    """Tests for GET /api/elections/results/ and /api/elections/results/<id>/"""

    def test_unauthenticated_returns_401(self):
        response = unauth_client().get("/api/elections/results/")
        assert response.status_code == 401

    def test_no_published_election(self):
        student = make_student()
        client = auth_client(student)
        response = client.get("/api/elections/results/")
        assert response.status_code == 404
        assert "No published results" in response.json()["error"]

    def test_results_for_published_election(self):
        student = make_student()
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get("/api/elections/results/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["election_name"] == "Test Election"

    def test_results_by_id(self):
        student = make_student()
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 200

    def test_unpublished_election_by_id_returns_403(self):
        student = make_student()
        election = make_election(status=Election.Status.ACTIVE)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 403
        assert "not yet published" in response.json()["error"]

    def test_nonexistent_election_returns_404(self):
        student = make_student()
        client = auth_client(student)
        import uuid
        response = client.get(f"/api/elections/results/{uuid.uuid4()}/")
        assert response.status_code == 404


# ── Cast Ballot ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCastBallotView:
    """Tests for POST /api/voting/cast/"""

    def setup_method(self):
        self.student = make_student()
        self.election = make_election()
        self.pos = make_position(self.election)
        self.cand = make_candidate(self.pos)
        make_eligible(self.student, self.election)
        self.client = auth_client(self.student)

    def _cast(self, election_id=None, selections=None):
        if election_id is None:
            election_id = str(self.election.pk)
        if selections is None:
            selections = [{"position_id": str(self.pos.pk), "candidate_id": str(self.cand.pk)}]
        return self.client.post(
            "/api/voting/cast/",
            data=json.dumps({"election_id": election_id, "selections": selections}),
            content_type="application/json",
        )

    def test_unauthenticated_returns_401(self):
        response = unauth_client().post(
            "/api/voting/cast/",
            data=json.dumps({"election_id": "x", "selections": []}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_successful_ballot_cast(self):
        response = self._cast()
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "ballot_id" in data

    def test_missing_election_id(self):
        response = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({"selections": [{"position_id": "x", "candidate_id": "y"}]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "election_id" in response.json()["error"]

    def test_missing_selections(self):
        response = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({"election_id": str(self.election.pk)}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_empty_selections(self):
        response = self.client.post(
            "/api/voting/cast/",
            data=json.dumps({"election_id": str(self.election.pk), "selections": []}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_invalid_json_body(self):
        response = self.client.post(
            "/api/voting/cast/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_malformed_selection_entry(self):
        response = self._cast(selections=[{"wrong_key": "value"}])
        assert response.status_code == 400
        assert "position_id" in response.json()["error"]

    def test_nonexistent_election(self):
        import uuid
        response = self._cast(election_id=str(uuid.uuid4()))
        assert response.status_code == 404

    def test_duplicate_ballot_returns_409(self):
        self._cast()
        response = self._cast()
        assert response.status_code == 409

    def test_closed_election_returns_409(self):
        self.election.status = Election.Status.CLOSED
        self.election.save()
        response = self._cast()
        assert response.status_code == 409

    def test_get_not_allowed(self):
        response = self.client.get("/api/voting/cast/")
        assert response.status_code == 405


# ── Admin Lifecycle Endpoints ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminLifecycleViews:
    """Tests for POST /api/admin/elections/start|close|publish/"""

    def setup_method(self):
        # Electoral Board Head — can start/close/publish
        self.eb_head_user, self.eb_head_profile = create_admin_user(
            username="ADMIN001",
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="Test EB Head",
        )
        self.admin_client = admin_client_for(self.eb_head_user)

        # Operator — cannot start/close/publish
        self.operator_user, self.operator_profile = create_admin_user(
            username="OPERATOR001",
            role=AdminRole.ELECTORAL_BOARD_OPERATOR,
            display_name="Test Operator",
        )
        self.operator_client = admin_client_for(self.operator_user)

        # Regular student — has no admin auth at all
        self.non_admin = make_student(student_id="STU001")
        self.student_client = auth_client(self.non_admin)

    def _post(self, client, url, election_id):
        return client.post(
            url,
            data=json.dumps({"election_id": str(election_id)}),
            content_type="application/json",
        )

    # ── Authentication & Authorization ──

    def test_unauthenticated_start_returns_401(self):
        election = make_election(status=Election.Status.DRAFT)
        response = unauth_client().post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_student_start_returns_401(self):
        """Student auth (session-based) must not grant admin access."""
        election = make_election(status=Election.Status.DRAFT)
        response = self._post(self.student_client, "/api/admin/elections/start/", election.pk)
        assert response.status_code == 401

    def test_operator_start_returns_403(self):
        """Operator role cannot start elections — only EB Head can."""
        election = make_election(status=Election.Status.DRAFT)
        response = self._post(self.operator_client, "/api/admin/elections/start/", election.pk)
        assert response.status_code == 403

    def test_operator_close_returns_403(self):
        election = make_election(status=Election.Status.ACTIVE)
        response = self._post(self.operator_client, "/api/admin/elections/close/", election.pk)
        assert response.status_code == 403

    def test_operator_publish_returns_403(self):
        election = make_election(status=Election.Status.CLOSED)
        response = self._post(self.operator_client, "/api/admin/elections/publish/", election.pk)
        assert response.status_code == 403

    # ── Successful transitions (EB Head only) ──

    def test_eb_head_starts_election(self):
        election = make_election(status=Election.Status.DRAFT)
        # Voter roll must be finalized before starting
        s = make_student(student_id="VROLL001")
        make_eligible(s, election)
        finalize_election_voter_roll(election)
        response = self._post(self.admin_client, "/api/admin/elections/start/", election.pk)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == Election.Status.ACTIVE

    def test_eb_head_closes_election(self):
        election = make_election(status=Election.Status.ACTIVE)
        response = self._post(self.admin_client, "/api/admin/elections/close/", election.pk)
        assert response.status_code == 200
        assert response.json()["status"] == Election.Status.CLOSED

    def test_eb_head_publishes_results(self):
        election = make_election(status=Election.Status.CLOSED)
        response = self._post(self.admin_client, "/api/admin/elections/publish/", election.pk)
        assert response.status_code == 200
        assert response.json()["status"] == Election.Status.PUBLISHED

    # ── Invalid transitions ──

    def test_invalid_transition_returns_409(self):
        election = make_election(status=Election.Status.DRAFT)
        response = self._post(self.admin_client, "/api/admin/elections/close/", election.pk)
        assert response.status_code == 409

    # ── Input validation ──

    def test_missing_election_id_returns_400(self):
        response = self.admin_client.post(
            "/api/admin/elections/start/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_nonexistent_election_returns_404(self):
        import uuid
        response = self._post(self.admin_client, "/api/admin/elections/start/", uuid.uuid4())
        assert response.status_code == 404

    def test_invalid_json_returns_400(self):
        response = self.admin_client.post(
            "/api/admin/elections/start/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_get_not_allowed(self):
        response = self.admin_client.get("/api/admin/elections/start/")
        assert response.status_code == 405


# ── Model Validation ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionTimeValidation:
    """Tests for Election.clean() time window validation."""

    def test_valid_time_window(self):
        election = Election(
            name="Valid",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        election.full_clean()  # Should not raise

    def test_end_before_start_raises(self):
        from django.core.exceptions import ValidationError
        election = Election(
            name="Invalid",
            start_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ValidationError, match="End time must be after"):
            election.full_clean()

    def test_equal_times_raises(self):
        from django.core.exceptions import ValidationError
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        election = Election(name="Equal", start_time=t, end_time=t)
        with pytest.raises(ValidationError, match="End time must be after"):
            election.full_clean()


@pytest.mark.django_db
class TestCandidateValidation:
    """Tests for Candidate model validation."""

    def test_house_college_without_college_raises(self):
        from django.core.exceptions import ValidationError
        election = make_election()
        pos = make_position(election, title="College Rep", category="house_college")
        candidate = Candidate(position=pos, full_name="No College")
        with pytest.raises(ValidationError, match="College is required"):
            candidate.full_clean()

    def test_house_college_with_college_passes(self):
        election = make_election()
        pos = make_position(election, title="College Rep", category="house_college")
        candidate = Candidate(
            position=pos, full_name="Has College", college="College of Engineering"
        )
        candidate.full_clean()  # Should not raise

    def test_executive_without_college_passes(self):
        election = make_election()
        pos = make_position(election, title="President", category="executive")
        candidate = Candidate(position=pos, full_name="No College Exec")
        candidate.full_clean()  # Should not raise

    def test_duplicate_candidate_name_per_position_raises(self):
        from django.db import IntegrityError
        election = make_election()
        pos = make_position(election)
        Candidate.objects.create(position=pos, full_name="Dup Name")
        with pytest.raises(IntegrityError):
            Candidate.objects.create(position=pos, full_name="Dup Name")


@pytest.mark.django_db
class TestAdminAuthDecoratorSeparation:
    """Tests that admin auth is separate from student auth on lifecycle endpoints."""

    def test_eb_head_can_access_lifecycle(self):
        """EB Head (via Django auth) can start elections."""
        user, _ = create_admin_user(
            username="ADM_DEC",
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="Dec Test Head",
        )
        election = make_election(status=Election.Status.DRAFT)
        s = make_student(student_id="VROLL002")
        make_eligible(s, election)
        finalize_election_voter_roll(election)
        client = admin_client_for(user)
        response = client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_student_auth_blocked_from_admin_endpoints(self):
        """Student session (even with is_admin=True) cannot access new admin endpoints."""
        student = make_student(student_id="NON_ADM")
        election = make_election(status=Election.Status.DRAFT)
        client = auth_client(student)
        response = client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_is_admin_defaults_false(self):
        s = Student.objects.create(
            student_id="DEF_ADM",
            full_name="Default Admin Test",
            date_of_birth=date(2000, 1, 1),
            course="Law",
            year=1,
        )
        assert s.is_admin is False
