"""
Tests for voting logic.

Covers:
- Ballot creation hashes student_id
- Cannot ballot twice per election (one-ballot-per-voter-per-election)
- Multiple selections per ballot
- Transactional integrity
- Ballot admin is read-only
"""
import pytest
from datetime import date, datetime, timezone

from django.db import IntegrityError

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotAlreadyCastError, VotingService


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_election(name="General Election 2026"):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=Election.Status.ACTIVE,
    )


def make_position(election, title="President", category=Position.Category.EXECUTIVE, max_selections=1, order=0):
    return Position.objects.create(
        election=election,
        title=title,
        category=category,
        max_selections=max_selections,
        order=order,
    )


def make_candidate(position, full_name="Candidate A", party="Party X"):
    return Candidate.objects.create(
        position=position,
        full_name=full_name,
        party=party,
    )


def make_student(student_id="VOTE001", full_name="Voter One"):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        date_of_birth=date(2001, 3, 10),
        course="Physics",
        year=2,
    )


# ── Ballot creation ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBallotCreation:
    """Test suite for ballot casting."""

    def setup_method(self) -> None:
        self.student = make_student()
        self.election = make_election()
        self.position = make_position(self.election)
        self.candidate = make_candidate(self.position)

    def test_cast_ballot_succeeds(self) -> None:
        """A valid ballot is recorded successfully."""
        ballot = VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        assert ballot is not None
        assert ballot.election == self.election

    def test_ballot_creates_selection(self) -> None:
        """Each (position, candidate) pair produces one BallotSelection."""
        ballot = VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        assert ballot.selections.count() == 1
        sel = ballot.selections.first()
        assert sel.position == self.position
        assert sel.candidate == self.candidate

    def test_ballot_hashes_student_id(self) -> None:
        """The stored hashed_student_id is not the raw student_id."""
        ballot = VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        assert ballot.hashed_student_id != self.student.student_id
        assert len(ballot.hashed_student_id) == 64  # SHA-256 hex

    def test_student_marked_has_voted(self) -> None:
        """After voting, student.has_voted is True."""
        VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        self.student.refresh_from_db()
        assert self.student.has_voted is True

    def test_cannot_ballot_twice_same_election(self) -> None:
        """A student cannot submit two ballots for the same election."""
        VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        with pytest.raises(BallotAlreadyCastError):
            VotingService.cast_ballot(
                self.student, self.election, [(self.position, self.candidate)]
            )

    def test_ballot_allowed_in_different_election(self) -> None:
        """A student may vote in a second, separate election."""
        election2 = make_election(name="By-Election 2026")
        pos2 = make_position(election2, title="Senator", category=Position.Category.SENATE)
        cand2 = make_candidate(pos2, full_name="Senator Candidate")

        VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        ballot2 = VotingService.cast_ballot(
            self.student, election2, [(pos2, cand2)]
        )
        assert ballot2 is not None

    def test_double_ballot_does_not_create_extra_record(self) -> None:
        """Failed duplicate ballot attempt leaves no dangling record."""
        VotingService.cast_ballot(
            self.student, self.election, [(self.position, self.candidate)]
        )
        try:
            VotingService.cast_ballot(
                self.student, self.election, [(self.position, self.candidate)]
            )
        except BallotAlreadyCastError:
            pass
        assert Ballot.objects.count() == 1

    def test_multi_position_ballot(self) -> None:
        """A single ballot can contain selections for multiple positions."""
        pos2 = make_position(
            self.election,
            title="Vice President",
            category=Position.Category.EXECUTIVE,
            order=1,
        )
        cand2 = make_candidate(pos2, full_name="VP Candidate")

        ballot = VotingService.cast_ballot(
            self.student,
            self.election,
            [(self.position, self.candidate), (pos2, cand2)],
        )
        assert ballot.selections.count() == 2


# ── Ballot model ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBallotModel:
    """Test suite for Ballot model methods."""

    def test_hash_student_id_returns_string(self) -> None:
        """hash_student_id returns a 64-char hex string."""
        result = Ballot.hash_student_id("TEST123")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_is_deterministic(self) -> None:
        """Same student_id always produces the same hash."""
        assert Ballot.hash_student_id("VOTE001") == Ballot.hash_student_id("VOTE001")

    def test_different_students_different_hashes(self) -> None:
        """Different student_ids produce different hashes."""
        assert Ballot.hash_student_id("VOTE001") != Ballot.hash_student_id("VOTE002")

    def test_hash_includes_salt(self) -> None:
        """Hash uses SECRET_KEY as salt, so raw SHA-256 of ID differs."""
        import hashlib

        raw_hash = hashlib.sha256("TEST123".encode()).hexdigest()
        salted_hash = Ballot.hash_student_id("TEST123")
        assert raw_hash != salted_hash

    def test_unique_constraint_ballot_per_voter_per_election(self) -> None:
        """DB-level unique constraint prevents two ballots for same voter+election."""
        election = make_election()
        hashed = Ballot.hash_student_id("STUDENT_X")

        Ballot.objects.create(election=election, hashed_student_id=hashed)
        with pytest.raises(IntegrityError):
            Ballot.objects.create(election=election, hashed_student_id=hashed)
