"""
Tests for election lifecycle management and result computation.

Covers:
- State machine transitions (DRAFT → ACTIVE → CLOSED → PUBLISHED)
- Invalid transition rejection
- Audit logging on transitions
- Result computation (executive majority, senate multi-seat, plurality)
- Zero-vote candidates included
- Edge cases (no votes, ties)
"""
import pytest
from datetime import date, datetime, timezone

from apps.accounts.models import Student
from apps.audit.models import AuditLog
from apps.elections.models import Candidate, Election, Position
from apps.elections.services import (
    ElectionLifecycleService,
    InvalidTransitionError,
    ResultService,
)
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotService


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_election(name="Test Election", status=Election.Status.DRAFT):
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


def make_student(student_id="LIFE001"):
    return Student.objects.create(
        student_id=student_id,
        full_name=f"Student {student_id}",
        date_of_birth=date(2001, 1, 1),
        course="Test", year=1,
    )


def cast_vote(student, election, selections):
    """Cast a ballot using string-ID tuples."""
    sel_tuples = [(str(pos.pk), str(cand.pk)) for pos, cand in selections]
    return BallotService.cast_ballot(student, election, sel_tuples)


# ── Lifecycle transitions ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionLifecycle:
    """Test the election state machine."""

    def test_draft_to_active(self) -> None:
        """DRAFT → ACTIVE succeeds."""
        election = make_election(status=Election.Status.DRAFT)
        result = ElectionLifecycleService.start_election(election)
        assert result.status == Election.Status.ACTIVE

    def test_active_to_closed(self) -> None:
        """ACTIVE → CLOSED succeeds."""
        election = make_election(status=Election.Status.ACTIVE)
        result = ElectionLifecycleService.close_election(election)
        assert result.status == Election.Status.CLOSED

    def test_closed_to_published(self) -> None:
        """CLOSED → PUBLISHED succeeds."""
        election = make_election(status=Election.Status.CLOSED)
        result = ElectionLifecycleService.publish_results(election)
        assert result.status == Election.Status.PUBLISHED

    def test_full_lifecycle(self) -> None:
        """DRAFT → ACTIVE → CLOSED → PUBLISHED full cycle."""
        election = make_election()
        election = ElectionLifecycleService.start_election(election)
        assert election.status == Election.Status.ACTIVE
        election = ElectionLifecycleService.close_election(election)
        assert election.status == Election.Status.CLOSED
        election = ElectionLifecycleService.publish_results(election)
        assert election.status == Election.Status.PUBLISHED

    def test_cannot_skip_active(self) -> None:
        """DRAFT → CLOSED is invalid."""
        election = make_election(status=Election.Status.DRAFT)
        with pytest.raises(InvalidTransitionError):
            ElectionLifecycleService.close_election(election)

    def test_cannot_skip_closed(self) -> None:
        """ACTIVE → PUBLISHED is invalid."""
        election = make_election(status=Election.Status.ACTIVE)
        with pytest.raises(InvalidTransitionError):
            ElectionLifecycleService.publish_results(election)

    def test_cannot_go_backwards(self) -> None:
        """CLOSED → ACTIVE is invalid."""
        election = make_election(status=Election.Status.CLOSED)
        with pytest.raises(InvalidTransitionError):
            ElectionLifecycleService.start_election(election)

    def test_published_is_terminal(self) -> None:
        """PUBLISHED cannot transition further."""
        election = make_election(status=Election.Status.PUBLISHED)
        with pytest.raises(InvalidTransitionError):
            ElectionLifecycleService.transition(election, "active")

    def test_transition_persists_to_db(self) -> None:
        """Status change is persisted to the database."""
        election = make_election(status=Election.Status.DRAFT)
        ElectionLifecycleService.start_election(election)
        election.refresh_from_db()
        assert election.status == Election.Status.ACTIVE

    def test_transition_creates_audit_log(self) -> None:
        """Each transition creates an audit log entry."""
        election = make_election(status=Election.Status.DRAFT)
        ElectionLifecycleService.start_election(
            election, performed_by="ADMIN001", ip_address="10.0.0.1"
        )
        log = AuditLog.objects.filter(
            event_type=AuditLog.EventType.ELECTION_STARTED
        ).first()
        assert log is not None
        assert log.student_id_attempted == "ADMIN001"
        assert log.success is True

    def test_close_creates_audit_log(self) -> None:
        """ACTIVE → CLOSED creates ELECTION_CLOSED audit log."""
        election = make_election(status=Election.Status.ACTIVE)
        ElectionLifecycleService.close_election(election, performed_by="ADMIN002")
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.ELECTION_CLOSED
        ).exists()

    def test_publish_creates_audit_log(self) -> None:
        """CLOSED → PUBLISHED creates RESULTS_PUBLISHED audit log."""
        election = make_election(status=Election.Status.CLOSED)
        ElectionLifecycleService.publish_results(election, performed_by="ADMIN003")
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.RESULTS_PUBLISHED
        ).exists()


# ── Result computation ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestResultComputation:
    """Test result calculation for various position categories."""

    def test_results_structure(self) -> None:
        """Results dict contains expected keys."""
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos)

        results = ResultService.compute_results(election)
        assert "election_id" in results
        assert "election_name" in results
        assert "positions" in results
        assert len(results["positions"]) == 1

    def test_executive_majority_win(self) -> None:
        """Executive candidate with >50% votes wins."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election, title="President", category="executive")
        cand_a = make_candidate(pos, full_name="Winner", party="A")
        cand_b = make_candidate(pos, full_name="Loser", party="B")

        # 3 votes for Winner, 1 for Loser → 75% majority
        for i in range(3):
            s = make_student(student_id=f"WIN{i:03d}")
            cast_vote(s, election, [(pos, cand_a)])
        s = make_student(student_id="LOSE001")
        cast_vote(s, election, [(pos, cand_b)])

        result = ResultService._compute_position_result(pos)
        assert result["winner"] == "Winner"
        assert result["status"] == "won"
        assert result["total_votes"] == 4

    def test_executive_no_majority(self) -> None:
        """Executive position with no candidate >50% returns no_majority."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election, title="President", category="executive")
        cand_a = make_candidate(pos, full_name="Cand A", party="A")
        cand_b = make_candidate(pos, full_name="Cand B", party="B")
        cand_c = make_candidate(pos, full_name="Cand C", party="C")

        # Each candidate gets 1 vote → no majority
        for i, cand in enumerate([cand_a, cand_b, cand_c]):
            s = make_student(student_id=f"MAJ{i:03d}")
            cast_vote(s, election, [(pos, cand)])

        result = ResultService._compute_position_result(pos)
        assert result["winner"] is None
        assert result["status"] == "no_majority"

    def test_senate_multi_seat(self) -> None:
        """Senate position: top N candidates by votes win."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(
            election, title="Senator", category="senate", max_selections=2
        )
        cand_a = make_candidate(pos, full_name="Sen A")
        cand_b = make_candidate(pos, full_name="Sen B")
        cand_c = make_candidate(pos, full_name="Sen C")

        # 3 voters each select 2 senators
        for i in range(2):
            s = make_student(student_id=f"SEN{i:03d}")
            cast_vote(s, election, [(pos, cand_a), (pos, cand_b)])
        s = make_student(student_id="SEN999")
        cast_vote(s, election, [(pos, cand_b), (pos, cand_c)])

        result = ResultService._compute_position_result(pos)
        assert result["status"] == "won"
        assert len(result["winner"]) == 2
        # cand_b has 3 votes, cand_a has 2 → top 2
        assert "Sen B" in result["winner"]
        assert "Sen A" in result["winner"]

    def test_plurality_winner(self) -> None:
        """House position: highest vote count wins."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(
            election, title="College Rep", category="house_college"
        )
        cand_a = make_candidate(pos, full_name="Rep A")
        cand_b = make_candidate(pos, full_name="Rep B")

        # Rep A gets 2 votes, Rep B gets 1
        for i in range(2):
            s = make_student(student_id=f"REP{i:03d}")
            cast_vote(s, election, [(pos, cand_a)])
        s = make_student(student_id="REP999")
        cast_vote(s, election, [(pos, cand_b)])

        result = ResultService._compute_position_result(pos)
        assert result["winner"] == "Rep A"
        assert result["status"] == "won"

    def test_no_votes_returns_no_votes(self) -> None:
        """Position with no votes cast returns no_votes status."""
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        make_candidate(pos, full_name="Lonely Cand")

        result = ResultService._compute_position_result(pos)
        assert result["winner"] is None
        assert result["status"] == "no_votes"
        assert result["total_votes"] == 0

    def test_zero_vote_candidates_included(self) -> None:
        """Active candidates with zero votes appear in results."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election, title="President", category="executive")
        cand_a = make_candidate(pos, full_name="Popular")
        cand_b = make_candidate(pos, full_name="Zero Votes")

        s = make_student()
        cast_vote(s, election, [(pos, cand_a)])

        result = ResultService._compute_position_result(pos)
        names = [r["candidate"] for r in result["results"]]
        assert "Popular" in names
        assert "Zero Votes" in names
        zero = next(r for r in result["results"] if r["candidate"] == "Zero Votes")
        assert zero["votes"] == 0

    def test_inactive_candidates_excluded_from_zero_votes(self) -> None:
        """Inactive candidates are NOT included in zero-vote list."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        make_candidate(pos, full_name="Active Cand")
        inactive = make_candidate(pos, full_name="Inactive Cand")
        inactive.is_active = False
        inactive.save()

        result = ResultService._compute_position_result(pos)
        names = [r["candidate"] for r in result["results"]]
        assert "Active Cand" in names
        assert "Inactive Cand" not in names

    def test_results_ordered_by_votes_descending(self) -> None:
        """Result candidates are ordered by vote count descending."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(
            election, title="Senator", category="senate", max_selections=3
        )
        cand_a = make_candidate(pos, full_name="Most Votes")
        cand_b = make_candidate(pos, full_name="Some Votes")
        cand_c = make_candidate(pos, full_name="Few Votes")

        # 3 votes for A, 2 for B, 1 for C
        for i in range(3):
            s = make_student(student_id=f"ORD{i:03d}")
            sels = [(pos, cand_a)]
            if i < 2:
                sels.append((pos, cand_b))
            if i < 1:
                sels.append((pos, cand_c))
            cast_vote(s, election, sels)

        result = ResultService._compute_position_result(pos)
        assert result["results"][0]["candidate"] == "Most Votes"
        assert result["results"][0]["votes"] == 3


# ── Decorator tests ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLoginRequiredDecorator:
    """Test the @login_required_student decorator."""

    def setup_method(self) -> None:
        from django.test import Client
        self.client = Client(enforce_csrf_checks=False)

    def test_unauthenticated_returns_401(self) -> None:
        """Accessing a protected endpoint without session returns 401."""
        response = self.client.get("/api/elections/current/")
        assert response.status_code == 401

    def test_authenticated_can_access(self) -> None:
        """Authenticated student can access protected endpoints."""
        student = make_student(student_id="DECO001")
        session = self.client.session
        session["authenticated_student_id"] = str(student.pk)
        session.save()
        response = self.client.get("/api/elections/status/")
        assert response.status_code == 200
