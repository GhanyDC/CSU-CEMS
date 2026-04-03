"""
Tests for voting logic.

Covers:
- Ballot creation hashes student_id
- Cannot ballot twice per election (one-ballot-per-voter-per-election)
- Multiple selections per ballot
- Transactional integrity
- Election status and time window validation
- Selection validation (position/candidate/max_selections)
- Ballot admin is read-only
"""
import pytest
from datetime import date, datetime, timezone

from django.db import IntegrityError

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import (
    BallotAlreadyCastError,
    BallotService,
    ElectionNotActiveError,
    InvalidSelectionError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_election(name="General Election 2026", status=Election.Status.ACTIVE):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
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


def _sel(position, candidate):
    """Helper: returns a (position_id, candidate_id) string tuple."""
    return (str(position.pk), str(candidate.pk))


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
        ballot = BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        assert ballot is not None
        assert ballot.election == self.election

    def test_ballot_creates_selection(self) -> None:
        """Each (position, candidate) pair produces one BallotSelection."""
        ballot = BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        assert ballot.selections.count() == 1
        sel = ballot.selections.first()
        assert sel.position == self.position
        assert sel.candidate == self.candidate

    def test_ballot_hashes_student_id(self) -> None:
        """The stored hashed_student_id is not the raw student_id."""
        ballot = BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        assert ballot.hashed_student_id != self.student.student_id
        assert len(ballot.hashed_student_id) == 64  # SHA-256 hex

    def test_cannot_ballot_twice_same_election(self) -> None:
        """A student cannot submit two ballots for the same election."""
        BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        with pytest.raises(BallotAlreadyCastError):
            BallotService.cast_ballot(
                self.student, self.election, [_sel(self.position, self.candidate)]
            )

    def test_ballot_allowed_in_different_election(self) -> None:
        """A student may vote in a second, separate election."""
        election2 = make_election(name="By-Election 2026")
        pos2 = make_position(election2, title="Senator", category=Position.Category.SENATE)
        cand2 = make_candidate(pos2, full_name="Senator Candidate")

        BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        ballot2 = BallotService.cast_ballot(
            self.student, election2, [_sel(pos2, cand2)]
        )
        assert ballot2 is not None

    def test_double_ballot_does_not_create_extra_record(self) -> None:
        """Failed duplicate ballot attempt leaves no dangling record."""
        BallotService.cast_ballot(
            self.student, self.election, [_sel(self.position, self.candidate)]
        )
        try:
            BallotService.cast_ballot(
                self.student, self.election, [_sel(self.position, self.candidate)]
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

        ballot = BallotService.cast_ballot(
            self.student,
            self.election,
            [_sel(self.position, self.candidate), _sel(pos2, cand2)],
        )
        assert ballot.selections.count() == 2


# ── Election validation ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionValidation:
    """Test election status and time window checks."""

    def setup_method(self) -> None:
        self.student = make_student()

    def test_draft_election_rejected(self) -> None:
        """Cannot vote in a DRAFT election."""
        election = make_election(status=Election.Status.DRAFT)
        pos = make_position(election)
        cand = make_candidate(pos)
        with pytest.raises(ElectionNotActiveError):
            BallotService.cast_ballot(self.student, election, [_sel(pos, cand)])

    def test_closed_election_rejected(self) -> None:
        """Cannot vote in a CLOSED election."""
        election = make_election(status=Election.Status.CLOSED)
        pos = make_position(election)
        cand = make_candidate(pos)
        with pytest.raises(ElectionNotActiveError):
            BallotService.cast_ballot(self.student, election, [_sel(pos, cand)])

    def test_published_election_rejected(self) -> None:
        """Cannot vote in a PUBLISHED election."""
        election = make_election(status=Election.Status.PUBLISHED)
        pos = make_position(election)
        cand = make_candidate(pos)
        with pytest.raises(ElectionNotActiveError):
            BallotService.cast_ballot(self.student, election, [_sel(pos, cand)])

    def test_expired_election_rejected(self) -> None:
        """Cannot vote in an election whose time window has passed."""
        election = Election.objects.create(
            name="Expired Election",
            start_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2020, 12, 31, tzinfo=timezone.utc),
            status=Election.Status.ACTIVE,
        )
        pos = make_position(election)
        cand = make_candidate(pos)
        with pytest.raises(ElectionNotActiveError):
            BallotService.cast_ballot(self.student, election, [_sel(pos, cand)])

    def test_future_election_rejected(self) -> None:
        """Cannot vote in an election that hasn't started yet."""
        election = Election.objects.create(
            name="Future Election",
            start_time=datetime(2099, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2099, 12, 31, tzinfo=timezone.utc),
            status=Election.Status.ACTIVE,
        )
        pos = make_position(election)
        cand = make_candidate(pos)
        with pytest.raises(ElectionNotActiveError):
            BallotService.cast_ballot(self.student, election, [_sel(pos, cand)])

    def test_empty_selections_rejected(self) -> None:
        """Cannot submit a ballot with no selections."""
        election = make_election()
        with pytest.raises(InvalidSelectionError):
            BallotService.cast_ballot(self.student, election, [])


# ── Selection validation ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSelectionValidation:
    """Test ballot selection validation rules."""

    def setup_method(self) -> None:
        self.student = make_student()
        self.election = make_election()
        self.position = make_position(self.election)
        self.candidate = make_candidate(self.position)

    def test_wrong_position_election_rejected(self) -> None:
        """Position from another election is rejected."""
        other_election = make_election(name="Other")
        other_pos = make_position(other_election, title="Other Position")
        other_cand = make_candidate(other_pos)
        with pytest.raises(InvalidSelectionError, match="does not belong"):
            BallotService.cast_ballot(
                self.student, self.election, [_sel(other_pos, other_cand)]
            )

    def test_wrong_candidate_position_rejected(self) -> None:
        """Candidate from another position is rejected."""
        pos2 = make_position(self.election, title="VP", order=2)
        cand2 = make_candidate(pos2, full_name="VP Cand")
        # Try to assign pos2's candidate to self.position
        with pytest.raises(InvalidSelectionError, match="not a valid"):
            BallotService.cast_ballot(
                self.student, self.election,
                [(str(self.position.pk), str(cand2.pk))]
            )

    def test_inactive_candidate_rejected(self) -> None:
        """Inactive candidate is rejected."""
        self.candidate.is_active = False
        self.candidate.save()
        with pytest.raises(InvalidSelectionError, match="not a valid"):
            BallotService.cast_ballot(
                self.student, self.election, [_sel(self.position, self.candidate)]
            )

    def test_exceeding_max_selections_rejected(self) -> None:
        """Exceeding max_selections for a position is rejected."""
        cand2 = make_candidate(self.position, full_name="Cand B")
        # position.max_selections = 1, but we select 2
        with pytest.raises(InvalidSelectionError, match="Too many selections"):
            BallotService.cast_ballot(
                self.student, self.election,
                [_sel(self.position, self.candidate), _sel(self.position, cand2)],
            )

    def test_multi_seat_allows_multiple_selections(self) -> None:
        """A position with max_selections > 1 allows multiple candidates."""
        senate = make_position(
            self.election, title="Senator",
            category=Position.Category.SENATE,
            max_selections=3, order=5,
        )
        c1 = make_candidate(senate, full_name="Sen A")
        c2 = make_candidate(senate, full_name="Sen B")
        c3 = make_candidate(senate, full_name="Sen C")
        ballot = BallotService.cast_ballot(
            self.student, self.election,
            [_sel(senate, c1), _sel(senate, c2), _sel(senate, c3)],
        )
        assert ballot.selections.count() == 3

    def test_duplicate_selection_pair_rejected(self) -> None:
        """Duplicate (position, candidate) pair is rejected."""
        # Use a multi-seat position so max_selections isn't hit first
        senate = make_position(
            self.election, title="Senator",
            category=Position.Category.SENATE,
            max_selections=3, order=5,
        )
        cand = make_candidate(senate, full_name="Sen Dup")
        with pytest.raises(InvalidSelectionError, match="Duplicate"):
            BallotService.cast_ballot(
                self.student, self.election,
                [_sel(senate, cand), _sel(senate, cand)],
            )


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

    def test_election_scoped_hash_differs(self) -> None:
        """Same student in different elections produces different hashes."""
        h1 = Ballot.hash_student_id("VOTE001", "election-a")
        h2 = Ballot.hash_student_id("VOTE001", "election-b")
        assert h1 != h2

    def test_unique_constraint_ballot_per_voter_per_election(self) -> None:
        """DB-level unique constraint prevents two ballots for same voter+election."""
        election = make_election()
        hashed = Ballot.hash_student_id("STUDENT_X", str(election.pk))

        Ballot.objects.create(election=election, hashed_student_id=hashed)
        with pytest.raises(IntegrityError):
            Ballot.objects.create(election=election, hashed_student_id=hashed)
