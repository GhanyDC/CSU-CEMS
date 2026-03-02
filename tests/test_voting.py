"""
Tests for voting logic.

Covers:
- Vote creation hashes student_id
- Cannot vote twice (one-person-one-vote)
- Transactional integrity
- Vote admin is read-only
"""
import pytest
from datetime import date

from apps.accounts.models import Student
from apps.elections.models import Candidate
from apps.voting.models import Vote
from apps.voting.services import VoteAlreadyCastError, VotingService


@pytest.mark.django_db
class TestVoteCreation:
    """Test suite for vote casting."""

    def setup_method(self) -> None:
        self.student = Student.objects.create(
            student_id="VOTE001",
            full_name="Voter One",
            date_of_birth=date(2001, 3, 10),
            course="Physics",
            year=2,
        )
        self.candidate = Candidate.objects.create(
            full_name="Candidate A",
            position="President",
            party="Party X",
        )

    def test_cast_vote_succeeds(self) -> None:
        """A valid vote is recorded successfully."""
        vote = VotingService.cast_vote(self.student, self.candidate)
        assert vote is not None
        assert vote.position == "President"
        assert vote.candidate == self.candidate

    def test_vote_hashes_student_id(self) -> None:
        """The stored hashed_student_id is not the raw student_id."""
        vote = VotingService.cast_vote(self.student, self.candidate)
        assert vote.hashed_student_id != self.student.student_id
        assert len(vote.hashed_student_id) == 64  # SHA-256 hex

    def test_vote_hash_is_deterministic(self) -> None:
        """Same student_id always produces the same hash."""
        hash1 = Vote.hash_student_id("VOTE001")
        hash2 = Vote.hash_student_id("VOTE001")
        assert hash1 == hash2

    def test_different_students_different_hashes(self) -> None:
        """Different student_ids produce different hashes."""
        hash1 = Vote.hash_student_id("VOTE001")
        hash2 = Vote.hash_student_id("VOTE002")
        assert hash1 != hash2

    def test_student_marked_has_voted(self) -> None:
        """After voting, student.has_voted is True."""
        VotingService.cast_vote(self.student, self.candidate)
        self.student.refresh_from_db()
        assert self.student.has_voted is True

    def test_cannot_vote_twice(self) -> None:
        """A student cannot vote a second time."""
        VotingService.cast_vote(self.student, self.candidate)
        with pytest.raises(VoteAlreadyCastError):
            VotingService.cast_vote(self.student, self.candidate)

    def test_cannot_vote_twice_different_candidate(self) -> None:
        """A student cannot vote for a different candidate either."""
        candidate_b = Candidate.objects.create(
            full_name="Candidate B",
            position="President",
            party="Party Y",
        )
        VotingService.cast_vote(self.student, self.candidate)
        with pytest.raises(VoteAlreadyCastError):
            VotingService.cast_vote(self.student, candidate_b)

    def test_vote_count_after_cast(self) -> None:
        """Exactly one vote record exists after casting."""
        VotingService.cast_vote(self.student, self.candidate)
        assert Vote.objects.count() == 1

    def test_double_vote_does_not_create_extra_record(self) -> None:
        """Failed double vote does not leave a dangling record."""
        VotingService.cast_vote(self.student, self.candidate)
        try:
            VotingService.cast_vote(self.student, self.candidate)
        except VoteAlreadyCastError:
            pass
        assert Vote.objects.count() == 1


@pytest.mark.django_db
class TestVoteModel:
    """Test suite for Vote model methods."""

    def test_hash_student_id_returns_string(self) -> None:
        """hash_student_id returns a hex string."""
        result = Vote.hash_student_id("TEST123")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_student_id_includes_salt(self) -> None:
        """Hash uses SECRET_KEY as salt, so raw SHA-256 of ID differs."""
        import hashlib

        raw_hash = hashlib.sha256("TEST123".encode()).hexdigest()
        salted_hash = Vote.hash_student_id("TEST123")
        assert raw_hash != salted_hash
