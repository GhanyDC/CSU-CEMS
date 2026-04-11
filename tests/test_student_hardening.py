"""
Tests for Student-Side Hardening Run 01.

Covers:
- Ballot state correctness (selections, abstain, mutual exclusivity)
- Submit payload matches ballot state (single source of truth)
- Duplicate ballot submission prevention via API
- Election state validation (ballot access only when Active)
- College representative filtering enforcement
- Session expiry / unauthenticated access handling
- Results visibility only after Published
- Already-voted student redirected from ballot
- Invalid election ID handling
- Multi-select position max selection enforcement
- All-abstain submission blocked
- Cross-college election isolation
- Frontend page rendering (200 for authenticated, redirect for anonymous)
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from django.test import Client

from apps.accounts.models import Student
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotService
from conftest import make_eligible


COLLEGES = list(OFFICIAL_COLLEGES)


def _make_student(student_id="SH_001", college=None, full_name="Hardening Student"):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        date_of_birth=date(2001, 3, 15),
        course="Test Course",
        year=2,
        college=college or COLLEGES[0],
    )


def _make_election(
    name="Test Election",
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


def _make_position(election, title="President", category="executive", max_selections=1, order=0):
    return Position.objects.create(
        election=election,
        title=title,
        category=category,
        max_selections=max_selections,
        order=order,
    )


def _make_candidate(position, full_name="Test Candidate", party="Test Party", college=""):
    return Candidate.objects.create(
        position=position,
        full_name=full_name,
        party=party,
        college=college,
    )


def _auth_client(student):
    """Return a test client authenticated as the given student."""
    client = Client(enforce_csrf_checks=False)
    session = client.session
    session["authenticated_student_id"] = str(student.pk)
    session.save()
    return client


def _sel(position, candidate):
    return (str(position.pk), str(candidate.pk))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Frontend Page Rendering
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestStudentPageRendering:
    """Student pages must render 200 for authenticated users and redirect otherwise."""

    def test_login_page_renders_for_anonymous(self):
        resp = Client().get("/")
        assert resp.status_code == 200
        assert b"Sign in" in resp.content or b"Welcome" in resp.content

    def test_dashboard_redirects_anonymous_to_login(self):
        resp = Client().get("/dashboard/")
        assert resp.status_code == 302
        assert "/" in resp.url

    def test_ballot_redirects_anonymous_to_login(self):
        resp = Client().get("/ballot/")
        assert resp.status_code == 302

    def test_results_redirects_anonymous_to_login(self):
        resp = Client().get("/results/")
        assert resp.status_code == 302

    def test_dashboard_renders_for_authenticated_student(self):
        student = _make_student()
        client = _auth_client(student)
        resp = client.get("/dashboard/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "dashboard" in content.lower() or "Dashboard" in content

    def test_ballot_renders_for_authenticated_student(self):
        student = _make_student(student_id="SH_BALLOT")
        client = _auth_client(student)
        resp = client.get("/ballot/")
        assert resp.status_code == 200

    def test_results_renders_for_authenticated_student(self):
        student = _make_student(student_id="SH_RESULTS")
        client = _auth_client(student)
        resp = client.get("/results/")
        assert resp.status_code == 200

    def test_viewport_meta_tag_present(self):
        """Base template should include viewport meta for responsive behavior."""
        resp = Client().get("/")
        content = resp.content.decode()
        assert 'viewport' in content
        assert 'width=device-width' in content


# ═══════════════════════════════════════════════════════════════════════════
# 2. Ballot API — State Validation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBallotStateValidation:
    """Ballot API must enforce election state and eligibility."""

    def test_ballot_blocked_for_draft_election(self):
        student = _make_student(student_id="SH_DRAFT")
        election = _make_election(status=Election.Status.DRAFT)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 403

    def test_ballot_blocked_for_closed_election(self):
        student = _make_student(student_id="SH_CLOSED")
        election = _make_election(status=Election.Status.CLOSED)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 403

    def test_ballot_blocked_for_published_election(self):
        student = _make_student(student_id="SH_PUB")
        election = _make_election(status=Election.Status.PUBLISHED)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 403

    def test_ballot_allowed_for_active_eligible_student(self):
        student = _make_student(student_id="SH_OK")
        election = _make_election()
        pos = _make_position(election)
        _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["has_voted"] is False

    def test_ballot_shows_has_voted_after_casting(self):
        student = _make_student(student_id="SH_VOTED")
        election = _make_election()
        pos = _make_position(election)
        cand = _make_candidate(pos)
        make_eligible(student, election)
        BallotService.cast_ballot(student, election, [_sel(pos, cand)])
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        assert resp.json()["has_voted"] is True

    def test_invalid_election_id_returns_404(self):
        student = _make_student(student_id="SH_BAD_ID")
        client = _auth_client(student)
        resp = client.get(f"/api/elections/{uuid.uuid4()}/ballot/")
        assert resp.status_code == 404

    def test_unauthenticated_ballot_returns_401(self):
        election = _make_election()
        resp = Client(enforce_csrf_checks=False).get(f"/api/elections/{election.pk}/ballot/")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 3. Vote Submission — Hardening
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestVoteSubmissionHardening:
    """Submit flow must be hardened against edge cases."""

    def test_duplicate_vote_returns_409(self):
        student = _make_student(student_id="SH_DUP")
        election = _make_election()
        pos = _make_position(election)
        cand = _make_candidate(pos)
        make_eligible(student, election)

        # First vote via service
        BallotService.cast_ballot(student, election, [_sel(pos, cand)])

        # Second vote via API
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 409

    def test_empty_selections_rejected(self):
        student = _make_student(student_id="SH_EMPTY")
        election = _make_election()
        make_eligible(student, election)
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_candidate_rejected(self):
        student = _make_student(student_id="SH_BAD_CAND")
        election = _make_election()
        pos = _make_position(election)
        _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(uuid.uuid4())}],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_position_rejected(self):
        student = _make_student(student_id="SH_BAD_POS")
        election = _make_election()
        pos = _make_position(election)
        cand = _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(uuid.uuid4()), "candidate_id": str(cand.pk)}],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 400

    def test_max_selections_enforced(self):
        """Cannot select more candidates than max_selections allows."""
        student = _make_student(student_id="SH_MAX")
        election = _make_election()
        pos = _make_position(election, title="VP", max_selections=1)
        cand1 = _make_candidate(pos, full_name="Cand A")
        cand2 = _make_candidate(pos, full_name="Cand B")
        make_eligible(student, election)
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [
                {"position_id": str(pos.pk), "candidate_id": str(cand1.pk)},
                {"position_id": str(pos.pk), "candidate_id": str(cand2.pk)},
            ],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 400
        assert "Too many" in resp.json()["error"]

    def test_voting_in_closed_election_rejected(self):
        student = _make_student(student_id="SH_CLOSED_V")
        election = _make_election(status=Election.Status.CLOSED)
        pos = _make_position(election)
        cand = _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 409

    def test_voting_without_eligibility_rejected(self):
        student = _make_student(student_id="SH_NOROLL")
        election = _make_election()
        pos = _make_position(election)
        cand = _make_candidate(pos)
        # NOT on voter roll
        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [{"position_id": str(pos.pk), "candidate_id": str(cand.pk)}],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 4. College Representative Filtering
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCollegeRepFiltering:
    """Backend must only return college rep candidates matching the student's college."""

    def test_college_rep_only_shows_own_college_candidates(self):
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student = _make_student(student_id="SH_REP_A", college=college_a)
        election = _make_election()
        pos = _make_position(election, title="College Rep", category="house_college")
        cand_a = _make_candidate(pos, full_name="Rep A", college=college_a)
        cand_b = _make_candidate(pos, full_name="Rep B", college=college_b)
        make_eligible(student, election)

        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        data = resp.json()
        assert data["success"] is True
        # Student from college A should only see Rep A
        position_data = data["positions"]
        rep_pos = [p for p in position_data if p["title"] == "College Rep"]
        assert len(rep_pos) == 1
        cand_names = [c["full_name"] for c in rep_pos[0]["candidates"]]
        assert "Rep A" in cand_names
        assert "Rep B" not in cand_names

    def test_college_rep_position_hidden_if_no_candidates(self):
        """If no candidates for s student's college, that position is skipped entirely."""
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student = _make_student(student_id="SH_REP_SKIP", college=college_a)
        election = _make_election()
        pos = _make_position(election, title="College Rep", category="house_college")
        # Only create candidate for college B
        _make_candidate(pos, full_name="Rep B Only", college=college_b)
        make_eligible(student, election)

        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        data = resp.json()
        # The position should be entirely absent
        pos_titles = [p["title"] for p in data["positions"]]
        assert "College Rep" not in pos_titles

    def test_campus_wide_positions_shown_to_all(self):
        """Non-college-rep positions in campus elections are shown to everyone."""
        student = _make_student(student_id="SH_CAMPUS", college=COLLEGES[0])
        election = _make_election()
        exec_pos = _make_position(election, title="President", category="executive")
        _make_candidate(exec_pos, full_name="Pres Candidate")
        make_eligible(student, election)

        client = _auth_client(student)
        resp = client.get(f"/api/elections/{election.pk}/ballot/")
        data = resp.json()
        pos_titles = [p["title"] for p in data["positions"]]
        assert "President" in pos_titles


# ═══════════════════════════════════════════════════════════════════════════
# 5. Cross-College Election Isolation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCrossCollegeIsolation:
    """Students cannot access elections from other colleges."""

    def test_student_cannot_vote_in_other_college_election(self):
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student = _make_student(student_id="SH_CROSS", college=college_a)
        election_b = _make_election(
            name="College B Elec",
            election_type=Election.ElectionType.COLLEGE,
            college=college_b,
        )
        pos = _make_position(election_b)
        cand = _make_candidate(pos)
        make_eligible(student, election_b)

        client = _auth_client(student)
        # Ballot access should be denied
        resp = client.get(f"/api/elections/{election_b.pk}/ballot/")
        assert resp.status_code == 403

    def test_other_college_election_not_in_mine_list(self):
        college_a = COLLEGES[0]
        college_b = COLLEGES[1]
        student = _make_student(student_id="SH_CROSS_MINE", college=college_a)
        election_b = _make_election(
            name="College B Elec 2",
            election_type=Election.ElectionType.COLLEGE,
            college=college_b,
        )
        make_eligible(student, election_b)

        client = _auth_client(student)
        resp = client.get("/api/elections/mine/")
        assert len(resp.json()["elections"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. Results Hardening
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestResultsHardening:
    """Results must only be visible after Published and to eligible students."""

    def test_results_blocked_before_publish(self):
        student = _make_student(student_id="SH_RES_ACT")
        election = _make_election(status=Election.Status.ACTIVE)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 403

    def test_results_blocked_for_ineligible_student(self):
        student = _make_student(student_id="SH_RES_INELIG")
        election = _make_election(status=Election.Status.PUBLISHED)
        # NOT on voter roll
        client = _auth_client(student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 403

    def test_results_available_for_published_eligible(self):
        student = _make_student(student_id="SH_RES_OK")
        election = _make_election(status=Election.Status.PUBLISHED)
        pos = _make_position(election)
        _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "positions" in data

    def test_results_include_turnout_and_thresholds(self):
        student = _make_student(student_id="SH_RES_DATA")
        election = _make_election(status=Election.Status.PUBLISHED)
        pos = _make_position(election)
        _make_candidate(pos)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get(f"/api/elections/results/{election.pk}/")
        data = resp.json()
        assert "total_eligible" in data
        assert "total_ballots" in data
        assert "turnout_percentage" in data

    def test_unauthenticated_results_returns_401(self):
        election = _make_election(status=Election.Status.PUBLISHED)
        resp = Client(enforce_csrf_checks=False).get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 7. Dashboard Eligibility Hardening
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDashboardEligibility:
    """Dashboard API must enforce eligibility and visibility rules."""

    def test_empty_dashboard_for_new_student(self):
        student = _make_student(student_id="SH_EMPTY_DASH")
        client = _auth_client(student)
        resp = client.get("/api/elections/mine/")
        data = resp.json()
        assert data["success"] is True
        assert data["elections"] == []

    def test_draft_elections_hidden(self):
        student = _make_student(student_id="SH_HIDDEN_DRAFT")
        election = _make_election(status=Election.Status.DRAFT)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get("/api/elections/mine/")
        assert len(resp.json()["elections"]) == 0

    def test_closed_elections_hidden(self):
        student = _make_student(student_id="SH_HIDDEN_CLOSED")
        election = _make_election(status=Election.Status.CLOSED)
        make_eligible(student, election)
        client = _auth_client(student)
        resp = client.get("/api/elections/mine/")
        assert len(resp.json()["elections"]) == 0

    def test_active_and_published_shown(self):
        student = _make_student(student_id="SH_BOTH")
        active = _make_election(name="Active", status=Election.Status.ACTIVE)
        published = _make_election(name="Published", status=Election.Status.PUBLISHED)
        make_eligible(student, active)
        make_eligible(student, published)
        client = _auth_client(student)
        resp = client.get("/api/elections/mine/")
        names = {e["name"] for e in resp.json()["elections"]}
        assert names == {"Active", "Published"}

    def test_has_voted_flag_accurate(self):
        student = _make_student(student_id="SH_VOTED_FLAG")
        election = _make_election()
        pos = _make_position(election)
        cand = _make_candidate(pos)
        make_eligible(student, election)

        client = _auth_client(student)
        # Before voting
        resp = client.get("/api/elections/mine/")
        assert resp.json()["elections"][0]["has_voted"] is False

        # After voting
        BallotService.cast_ballot(student, election, [_sel(pos, cand)])
        resp = client.get("/api/elections/mine/")
        assert resp.json()["elections"][0]["has_voted"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 8. Multi-Position Ballot Correctness
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMultiPositionBallot:
    """Verify multi-position and multi-select ballot submission correctness."""

    def test_multi_position_ballot_accepted(self):
        student = _make_student(student_id="SH_MULTI_POS")
        election = _make_election()
        pos1 = _make_position(election, title="President", order=1)
        pos2 = _make_position(election, title="VP", order=2)
        cand1 = _make_candidate(pos1, full_name="Pres A")
        cand2 = _make_candidate(pos2, full_name="VP A")
        make_eligible(student, election)

        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [
                {"position_id": str(pos1.pk), "candidate_id": str(cand1.pk)},
                {"position_id": str(pos2.pk), "candidate_id": str(cand2.pk)},
            ],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 201
        assert resp.json()["success"] is True

    def test_multi_select_position_multiple_candidates(self):
        """For Senators (max 12), selecting multiple candidates is valid."""
        student = _make_student(student_id="SH_MULTI_SEL")
        election = _make_election()
        pos = _make_position(election, title="Senator", category="senate", max_selections=12)
        candidates = []
        for i in range(5):
            candidates.append(_make_candidate(pos, full_name=f"Senator {i}"))
        make_eligible(student, election)

        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [
                {"position_id": str(pos.pk), "candidate_id": str(c.pk)}
                for c in candidates[:3]  # Select 3 of 5
            ],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 201

        # Verify 3 selections stored
        ballot = Ballot.objects.get(election=election)
        selections = BallotSelection.objects.filter(ballot=ballot)
        assert selections.count() == 3

    def test_partial_ballot_accepted(self):
        """Can submit ballot without voting for every position (implicit abstain)."""
        student = _make_student(student_id="SH_PARTIAL")
        election = _make_election()
        pos1 = _make_position(election, title="President", order=1)
        pos2 = _make_position(election, title="VP", order=2)
        cand1 = _make_candidate(pos1, full_name="Pres Only")
        _make_candidate(pos2, full_name="VP Skip")
        make_eligible(student, election)

        client = _auth_client(student)
        # Only vote for position 1 (implicit abstain on position 2)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [
                {"position_id": str(pos1.pk), "candidate_id": str(cand1.pk)},
            ],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 201

    def test_duplicate_candidate_in_same_selection_rejected(self):
        """Cannot select the same candidate twice."""
        student = _make_student(student_id="SH_DUP_CAND")
        election = _make_election()
        pos = _make_position(election, title="Senator", category="senate", max_selections=12)
        cand = _make_candidate(pos, full_name="Dup Check")
        make_eligible(student, election)

        client = _auth_client(student)
        payload = json.dumps({
            "election_id": str(election.pk),
            "selections": [
                {"position_id": str(pos.pk), "candidate_id": str(cand.pk)},
                {"position_id": str(pos.pk), "candidate_id": str(cand.pk)},
            ],
        })
        resp = client.post("/api/voting/cast/", payload, content_type="application/json")
        assert resp.status_code == 400
        assert "Duplicate" in resp.json()["error"]
