"""
Tests for model integrity and constraints.
"""
import pytest
from datetime import date, datetime, timezone

from django.db import IntegrityError

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_election(name="Test Election", status=Election.Status.ACTIVE):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
    )


def make_position(election, title="President", category=Position.Category.EXECUTIVE):
    return Position.objects.create(
        election=election,
        title=title,
        category=category,
        max_selections=1,
        order=0,
    )


# ── Student ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentModel:
    """Test Student model constraints and methods."""

    def test_student_id_is_unique(self) -> None:
        """Duplicate student_id raises IntegrityError."""
        Student.objects.create(
            student_id="UNIQ001",
            full_name="First",
            date_of_birth=date(2000, 1, 1),
            course="Art",
            year=1,
        )
        with pytest.raises(IntegrityError):
            Student.objects.create(
                student_id="UNIQ001",
                full_name="Second",
                date_of_birth=date(2000, 2, 2),
                course="Art",
                year=1,
            )

    def test_failed_attempts_defaults_zero(self) -> None:
        """New students default to failed_attempts=0."""
        s = Student.objects.create(
            student_id="DEF002",
            full_name="Default2",
            date_of_birth=date(2000, 1, 1),
            course="Law",
            year=1,
        )
        assert s.failed_attempts == 0

    def test_str_representation(self) -> None:
        """__str__ includes student_id and full_name."""
        s = Student.objects.create(
            student_id="STR001",
            full_name="String Test",
            date_of_birth=date(2000, 1, 1),
            course="Music",
            year=1,
        )
        assert "STR001" in str(s)
        assert "String Test" in str(s)


# ── Election ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestElectionModel:
    """Test Election model."""

    def test_election_creation(self) -> None:
        """Election can be created with required fields."""
        election = make_election()
        assert election.status == Election.Status.ACTIVE

    def test_election_default_status_is_draft(self) -> None:
        """Newly created election without explicit status defaults to draft."""
        election = Election.objects.create(
            name="Draft Election",
            start_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
        assert election.status == Election.Status.DRAFT

    def test_str_representation(self) -> None:
        """__str__ includes name and status label."""
        election = make_election(name="General Elections")
        assert "General Elections" in str(election)
        assert "Active" in str(election)


# ── Position ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPositionModel:
    """Test Position model."""

    def test_position_creation(self) -> None:
        """Position can be created linked to an election."""
        election = make_election()
        pos = make_position(election, title="Vice President")
        assert pos.election == election
        assert pos.max_selections == 1

    def test_unique_title_per_election(self) -> None:
        """Two positions with the same title in the same election raise IntegrityError."""
        election = make_election()
        make_position(election, title="Senator")
        with pytest.raises(IntegrityError):
            make_position(election, title="Senator")

    def test_same_title_different_elections(self) -> None:
        """The same title is allowed across different elections."""
        e1 = make_election(name="Election A")
        e2 = make_election(name="Election B")
        p1 = make_position(e1, title="President")
        p2 = make_position(e2, title="President")
        assert p1.pk != p2.pk

    def test_str_representation(self) -> None:
        """__str__ includes position title and election name."""
        election = make_election(name="2026 Election")
        pos = make_position(election, title="Treasurer")
        assert "Treasurer" in str(pos)
        assert "2026 Election" in str(pos)


# ── Candidate ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCandidateModel:
    """Test Candidate model."""

    def setup_method(self) -> None:
        self.election = make_election()
        self.position = make_position(self.election)

    def test_candidate_creation(self) -> None:
        """Candidate can be created linked to a position."""
        c = Candidate.objects.create(
            position=self.position,
            full_name="Test Candidate",
        )
        assert c.is_active is True
        assert c.party == ""
        assert c.college is None

    def test_candidate_with_college(self) -> None:
        """Candidate can store a college affiliation."""
        pos = make_position(
            self.election,
            title="College Rep – Engineering",
            category=Position.Category.HOUSE_COLLEGE,
        )
        c = Candidate.objects.create(
            position=pos,
            full_name="College Rep",
            college="College of Engineering",
        )
        assert c.college == "College of Engineering"

    def test_str_representation(self) -> None:
        """__str__ includes candidate name and position title."""
        c = Candidate.objects.create(
            position=self.position,
            full_name="Named Candidate",
        )
        assert "Named Candidate" in str(c)
        assert self.position.title in str(c)
