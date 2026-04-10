"""
Tests for Bundle 04: Student Voting, Results & Monitoring.

Covers:
- Student dashboard eligibility (my_elections endpoint)
- Campus vs college election visibility
- Cross-college access denied
- Election ballot structure endpoint
- One-ballot-per-election enforcement (via casting)
- Results visibility rules (Active→none, Closed→admin-only, Published→students)
- Results include 50%+1 thresholds and turnout data
- Admin monitoring: turnout endpoint
- Admin monitoring: tally blocked during Active, available after Close
- Role enforcement on monitoring endpoints
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from django.test import Client

from apps.accounts.models import AdminRole, Student
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.elections.services import ResultService, TurnoutService
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotService
from conftest import (
    admin_client_for,
    create_admin_user,
    finalize_election_voter_roll,
    make_eligible,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

COLLEGES = list(OFFICIAL_COLLEGES)


def make_student(student_id="B04_001", full_name="Bundle4 Student", college=None):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        date_of_birth=date(2001, 1, 1),
        course="Test",
        year=2,
        college=college or "",
    )


def make_election(
    name="Campus Election 2026",
    status=Election.Status.ACTIVE,
    election_type=Election.ElectionType.CAMPUS,
    college="",
):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
        election_type=election_type,
        college=college,
    )


def make_position(election, title="President", category="executive", max_selections=1, order=0):
    return Position.objects.create(
        election=election,
        title=title,
        category=category,
        max_selections=max_selections,
        order=order,
    )


def make_candidate(position, full_name="Candidate A", party="Party X", college=""):
    return Candidate.objects.create(
        position=position,
        full_name=full_name,
        party=party,
        college=college,
    )


def auth_client(student):
    """Return a test client authenticated as the given student."""
    client = Client(enforce_csrf_checks=False)
    session = client.session
    session["authenticated_student_id"] = str(student.pk)
    session.save()
    return client


def unauth_client():
    return Client(enforce_csrf_checks=False)


def _sel(position, candidate):
    return (str(position.pk), str(candidate.pk))


# ── My Elections (Dashboard Eligibility) ──────────────────────────────────────

@pytest.mark.django_db
class TestMyElections:
    """Tests for GET /api/elections/mine/"""

    def test_unauthenticated_returns_401(self):
        response = unauth_client().get("/api/elections/mine/")
        assert response.status_code == 401

    def test_no_eligible_elections(self):
        student = make_student()
        client = auth_client(student)
        response = client.get("/api/elections/mine/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["elections"] == []

    def test_returns_active_election_for_eligible_student(self):
        student = make_student(college=COLLEGES[0])
        election = make_election()
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get("/api/elections/mine/")
        data = response.json()
        assert len(data["elections"]) == 1
        assert data["elections"][0]["name"] == "Campus Election 2026"
        assert data["elections"][0]["status"] == "active"
        assert data["elections"][0]["has_voted"] is False

    def test_returns_published_election_for_eligible_student(self):
        student = make_student(college=COLLEGES[0])
        election = make_election(status=Election.Status.PUBLISHED)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get("/api/elections/mine/")
        data = response.json()
        assert len(data["elections"]) == 1
        assert data["elections"][0]["status"] == "published"

    def test_draft_and_closed_elections_not_shown(self):
        student = make_student()
        draft = make_election(name="Draft", status=Election.Status.DRAFT)
        closed = make_election(name="Closed", status=Election.Status.CLOSED)
        make_eligible(student, draft)
        make_eligible(student, closed)
        client = auth_client(student)

        response = client.get("/api/elections/mine/")
        assert len(response.json()["elections"]) == 0

    def test_ineligible_student_sees_nothing(self):
        student = make_student()
        other = make_student(student_id="B04_OTHER")
        election = make_election()
        make_eligible(other, election)  # other student, not our student
        client = auth_client(student)

        response = client.get("/api/elections/mine/")
        assert len(response.json()["elections"]) == 0

    def test_has_voted_flag_after_casting(self):
        student = make_student(college=COLLEGES[0])
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)
        make_eligible(student, election)

        BallotService.cast_ballot(student, election, [_sel(pos, cand)])

        client = auth_client(student)
        response = client.get("/api/elections/mine/")
        assert response.json()["elections"][0]["has_voted"] is True

    def test_both_campus_and_college_elections_shown(self):
        college = COLLEGES[0]
        student = make_student(college=college)
        campus = make_election(name="Campus 2026")
        college_el = make_election(
            name="College 2026",
            election_type=Election.ElectionType.COLLEGE,
            college=college,
        )
        make_eligible(student, campus)
        make_eligible(student, college_el)

        client = auth_client(student)
        data = client.get("/api/elections/mine/").json()
        names = {e["name"] for e in data["elections"]}
        assert names == {"Campus 2026", "College 2026"}


# ── College Election Isolation ─────────────────────────────────────────────

@pytest.mark.django_db
class TestCollegeIsolation:
    """Students cannot access another college's election."""

    def test_student_cannot_see_other_college_election(self):
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student_a = make_student(student_id="COL_A", college=college_a)

        # Create a college election for college B
        election_b = make_election(
            name="College B Election",
            election_type=Election.ElectionType.COLLEGE,
            college=college_b,
        )
        # Even if accidentally added to voter roll, college mismatch blocks
        make_eligible(student_a, election_b)

        client = auth_client(student_a)
        response = client.get("/api/elections/mine/")
        assert len(response.json()["elections"]) == 0

    def test_student_cannot_access_other_college_ballot(self):
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student_a = make_student(student_id="COL_A2", college=college_a)

        election_b = make_election(
            name="College B Election 2",
            election_type=Election.ElectionType.COLLEGE,
            college=college_b,
        )
        make_eligible(student_a, election_b)

        client = auth_client(student_a)
        response = client.get(f"/api/elections/{election_b.pk}/ballot/")
        assert response.status_code == 403
        assert "not eligible" in response.json()["error"]

    def test_same_college_student_can_access_ballot(self):
        college = COLLEGES[0]
        student = make_student(student_id="COL_OK", college=college)

        election = make_election(
            name="My College Election",
            election_type=Election.ElectionType.COLLEGE,
            college=college,
        )
        pos = make_position(election, title="Rep", category="house_college")
        cand = make_candidate(pos, college=college)
        make_eligible(student, election)

        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["positions"]) == 1


# ── Election Ballot Endpoint ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionBallot:
    """Tests for GET /api/elections/<id>/ballot/"""

    def test_unauthenticated_returns_401(self):
        election = make_election()
        response = unauth_client().get(f"/api/elections/{election.pk}/ballot/")
        assert response.status_code == 401

    def test_nonexistent_election_returns_404(self):
        student = make_student()
        client = auth_client(student)
        response = client.get(f"/api/elections/{uuid.uuid4()}/ballot/")
        assert response.status_code == 404

    def test_non_active_election_returns_403(self):
        student = make_student()
        election = make_election(status=Election.Status.DRAFT)
        make_eligible(student, election)
        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        assert response.status_code == 403
        assert "not currently active" in response.json()["error"]

    def test_ineligible_student_returns_403(self):
        student = make_student()
        election = make_election()
        # Not on voter roll
        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        assert response.status_code == 403

    def test_returns_ballot_structure(self):
        student = make_student()
        election = make_election()
        pos1 = make_position(election, title="President", order=1)
        pos2 = make_position(election, title="VP", order=2)
        c1a = make_candidate(pos1, full_name="Alice")
        c1b = make_candidate(pos1, full_name="Bob")
        c2a = make_candidate(pos2, full_name="Charlie")
        make_eligible(student, election)

        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["has_voted"] is False
        assert len(data["positions"]) == 2
        assert data["positions"][0]["title"] == "President"
        assert len(data["positions"][0]["candidates"]) == 2
        assert data["positions"][1]["title"] == "VP"

    def test_has_voted_flag_true_after_voting(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)
        make_eligible(student, election)

        BallotService.cast_ballot(student, election, [_sel(pos, cand)])

        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        assert response.json()["has_voted"] is True

    def test_inactive_candidates_excluded(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        active_cand = make_candidate(pos, full_name="Active")
        inactive_cand = make_candidate(pos, full_name="Inactive")
        inactive_cand.is_active = False
        inactive_cand.save()
        make_eligible(student, election)

        client = auth_client(student)
        response = client.get(f"/api/elections/{election.pk}/ballot/")
        cand_names = [c["full_name"] for c in response.json()["positions"][0]["candidates"]]
        assert "Active" in cand_names
        assert "Inactive" not in cand_names


# ── Results Visibility Rules ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestResultsVisibility:
    """
    Active = no results for anyone
    Closed = admin-only (via tally endpoint)
    Published = students can see results
    """

    def test_active_election_results_returns_403(self):
        student = make_student()
        election = make_election(status=Election.Status.ACTIVE)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 403
        assert "not yet published" in response.json()["error"]

    def test_closed_election_results_returns_403_for_student(self):
        student = make_student()
        election = make_election(status=Election.Status.CLOSED)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 403

    def test_published_election_results_available(self):
        student = make_student()
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["election_name"] == "Campus Election 2026"

    def test_ineligible_student_cannot_see_published_results(self):
        student = make_student(student_id="NOPE01")
        election = make_election(status=Election.Status.PUBLISHED)
        # Not on voter roll
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        assert response.status_code == 403

    def test_results_include_threshold_data(self):
        student = make_student()
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        make_eligible(student, election)
        client = auth_client(student)

        response = client.get(f"/api/elections/results/{election.pk}/")
        data = response.json()
        assert "total_eligible" in data
        assert "total_ballots" in data
        assert "turnout_percentage" in data
        # Position-level threshold data
        assert "threshold_50_plus_1" in data["positions"][0]
        assert "threshold_denominator" in data["positions"][0]

    def test_results_threshold_values_correct(self):
        """50%+1 of 10 eligible = 6."""
        students = []
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        cand = make_candidate(pos)

        for i in range(10):
            s = make_student(student_id=f"THR{i:03d}")
            students.append(s)
            make_eligible(s, election)

        # Cast 7 ballots while election is Active
        for s in students[:7]:
            BallotService.cast_ballot(s, election, [_sel(pos, cand)])

        # Transition to Published so compute_results_with_thresholds works
        election.status = Election.Status.PUBLISHED
        election.save()

        data = ResultService.compute_results_with_thresholds(election)
        assert data["total_eligible"] == 10
        assert data["total_ballots"] == 7
        assert data["positions"][0]["threshold_denominator"] == 10
        assert data["positions"][0]["threshold_50_plus_1"] == 6  # 10//2 + 1

    def test_fallback_results_finds_published_election(self):
        """GET /api/elections/results/ (no ID) finds most recent published."""
        student = make_student()
        election = make_election(name="Published One", status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        make_eligible(student, election)

        client = auth_client(student)
        response = client.get("/api/elections/results/")
        assert response.status_code == 200
        assert response.json()["election_name"] == "Published One"


# ── Admin Monitoring: Turnout ────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionTurnout:
    """Tests for GET /api/admin/elections/<id>/turnout/"""

    def setup_method(self):
        self.eb_user, _ = create_admin_user(
            username="TURN_EB", role=AdminRole.ELECTORAL_BOARD_HEAD
        )
        self.admin_client = admin_client_for(self.eb_user)

    def test_unauthenticated_returns_401(self):
        election = make_election()
        response = unauth_client().get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 401

    def test_student_cannot_access_turnout(self):
        student = make_student(student_id="NO_TURN")
        election = make_election()
        client = auth_client(student)
        response = client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 401

    def test_active_election_turnout(self):
        election = make_election(status=Election.Status.ACTIVE)
        s1 = make_student(student_id="T001", college=COLLEGES[0])
        s2 = make_student(student_id="T002", college=COLLEGES[1])
        make_eligible(s1, election)
        make_eligible(s2, election)

        pos = make_position(election)
        cand = make_candidate(pos)
        BallotService.cast_ballot(s1, election, [_sel(pos, cand)])

        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 200
        data = response.json()
        assert data["total_eligible"] == 2
        assert data["total_voted"] == 1
        assert data["turnout_percentage"] == 50.0

    def test_draft_election_turnout_returns_403(self):
        election = make_election(status=Election.Status.DRAFT)
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 403

    def test_turnout_does_not_expose_candidate_tallies(self):
        election = make_election()
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        data = response.json()
        assert "positions" not in data
        assert "results" not in data
        assert "candidates" not in data

    def test_nonexistent_election_returns_404(self):
        response = self.admin_client.get(f"/api/admin/elections/{uuid.uuid4()}/turnout/")
        assert response.status_code == 404

    def test_by_college_breakdown(self):
        election = make_election()
        s1 = make_student(student_id="BC01", college=COLLEGES[0])
        s2 = make_student(student_id="BC02", college=COLLEGES[1])
        s3 = make_student(student_id="BC03", college=COLLEGES[0])
        make_eligible(s1, election)
        make_eligible(s2, election)
        make_eligible(s3, election)

        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/turnout/")
        data = response.json()
        college_names = {c["college"] for c in data["by_college"]}
        assert COLLEGES[0] in college_names
        assert COLLEGES[1] in college_names


# ── Admin Monitoring: Tally Review ────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionTallyReview:
    """Tests for GET /api/admin/elections/<id>/tally/"""

    def setup_method(self):
        self.eb_user, _ = create_admin_user(
            username="TALLY_EB", role=AdminRole.ELECTORAL_BOARD_HEAD
        )
        self.admin_client = admin_client_for(self.eb_user)

    def test_active_election_tally_blocked(self):
        """EB Head CAN see live tally during Active (updated requirement)."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        make_candidate(pos)
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_active_election_tally_blocked_for_non_eb_head(self):
        """Non-EB-Head roles cannot see live tally during Active."""
        op_user, _ = create_admin_user(
            username="TALLY_OP", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        op_client = admin_client_for(op_user)
        election = make_election(status=Election.Status.ACTIVE)
        response = op_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 403

    def test_closed_election_tally_available(self):
        election = make_election(status=Election.Status.CLOSED)
        pos = make_position(election)
        make_candidate(pos)
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "positions" in data

    def test_published_election_tally_available(self):
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_draft_election_tally_blocked(self):
        election = make_election(status=Election.Status.DRAFT)
        response = self.admin_client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self):
        election = make_election()
        response = unauth_client().get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 401


# ── Role Enforcement on Monitoring Endpoints ──────────────────────────────────

@pytest.mark.django_db
class TestMonitoringRoleEnforcement:
    """Monitoring endpoints require specific admin roles."""

    def test_tally_watcher_can_access_turnout(self):
        watcher_user, _ = create_admin_user(
            username="WATCH01", role=AdminRole.TALLY_WATCHER
        )
        election = make_election()
        client = admin_client_for(watcher_user)
        response = client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 200

    def test_auditor_cannot_access_turnout(self):
        """AUDITOR role is no longer granted turnout access."""
        auditor_user, _ = create_admin_user(
            username="AUDIT01", role=AdminRole.AUDITOR
        )
        election = make_election()
        client = admin_client_for(auditor_user)
        response = client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 403

    def test_technical_support_cannot_access_turnout(self):
        tech_user, _ = create_admin_user(
            username="TECH01", role=AdminRole.TECHNICAL_SUPPORT
        )
        election = make_election()
        client = admin_client_for(tech_user)
        response = client.get(f"/api/admin/elections/{election.pk}/turnout/")
        assert response.status_code == 403

    def test_technical_support_cannot_access_tally(self):
        tech_user, _ = create_admin_user(
            username="TECH02", role=AdminRole.TECHNICAL_SUPPORT
        )
        election = make_election(status=Election.Status.CLOSED)
        client = admin_client_for(tech_user)
        response = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 403

    def test_operator_can_access_tally(self):
        op_user, _ = create_admin_user(
            username="OP01", role=AdminRole.ELECTORAL_BOARD_OPERATOR
        )
        election = make_election(status=Election.Status.CLOSED)
        pos = make_position(election)
        make_candidate(pos)
        client = admin_client_for(op_user)
        response = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert response.status_code == 200


# ── TurnoutService Unit Tests ────────────────────────────────────────────────

@pytest.mark.django_db
class TestTurnoutService:
    """Unit tests for TurnoutService.compute_turnout()."""

    def test_empty_election(self):
        election = make_election()
        result = TurnoutService.compute_turnout(election)
        assert result["total_eligible"] == 0
        assert result["total_voted"] == 0
        assert result["turnout_percentage"] == 0

    def test_correct_counts(self):
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)

        students = []
        for i in range(5):
            s = make_student(student_id=f"TS{i:03d}", college=COLLEGES[0])
            make_eligible(s, election)
            students.append(s)

        # 3 out of 5 vote
        for s in students[:3]:
            BallotService.cast_ballot(s, election, [_sel(pos, cand)])

        result = TurnoutService.compute_turnout(election)
        assert result["total_eligible"] == 5
        assert result["total_voted"] == 3
        assert result["turnout_percentage"] == 60.0


# ── One Ballot Per Election (Integration) ────────────────────────────────────

@pytest.mark.django_db
class TestOneBallotPerElection:
    """Ensure a student cannot cast a second ballot in the same election."""

    def test_duplicate_ballot_rejected_via_api(self):
        student = make_student()
        election = make_election()
        pos = make_position(election)
        cand = make_candidate(pos)
        make_eligible(student, election)

        client = auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })

        # First ballot succeeds
        resp1 = client.post("/api/voting/cast/", data=payload, content_type="application/json")
        assert resp1.status_code == 201

        # Second ballot fails
        resp2 = client.post("/api/voting/cast/", data=payload, content_type="application/json")
        assert resp2.status_code == 409

    def test_can_vote_in_different_elections(self):
        student = make_student(college=COLLEGES[0])
        campus = make_election(name="Campus")
        college_el = make_election(
            name="College",
            election_type=Election.ElectionType.COLLEGE,
            college=COLLEGES[0],
        )

        pos_c = make_position(campus, title="President")
        cand_c = make_candidate(pos_c)
        make_eligible(student, campus)

        pos_col = make_position(college_el, title="Rep", category="house_college")
        cand_col = make_candidate(pos_col, college=COLLEGES[0])
        make_eligible(student, college_el)

        # Both ballots succeed
        b1 = BallotService.cast_ballot(student, campus, [_sel(pos_c, cand_c)])
        b2 = BallotService.cast_ballot(student, college_el, [_sel(pos_col, cand_col)])
        assert b1 is not None
        assert b2 is not None


# ── Compute Results With Thresholds (Unit) ───────────────────────────────────

@pytest.mark.django_db
class TestComputeResultsWithThresholds:
    """Unit tests for ResultService.compute_results_with_thresholds()."""

    def test_basic_structure(self):
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos, full_name="A")
        make_candidate(pos, full_name="B")

        s = make_student()
        make_eligible(s, election)

        result = ResultService.compute_results_with_thresholds(election)
        assert "total_eligible" in result
        assert "total_ballots" in result
        assert "turnout_percentage" in result
        assert "positions" in result
        assert "threshold_50_plus_1" in result["positions"][0]
        assert "threshold_denominator" in result["positions"][0]

    def test_turnout_percentage_calculated(self):
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        cand = make_candidate(pos)

        for i in range(4):
            s = make_student(student_id=f"RWH{i:03d}")
            make_eligible(s, election)
            if i < 2:
                BallotService.cast_ballot(s, election, [_sel(pos, cand)])

        election.status = Election.Status.PUBLISHED
        election.save()

        result = ResultService.compute_results_with_thresholds(election)
        assert result["total_eligible"] == 4
        assert result["total_ballots"] == 2
        assert result["turnout_percentage"] == 50.0
