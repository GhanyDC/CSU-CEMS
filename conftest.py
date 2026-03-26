"""
Shared test configuration and fixtures.
"""
import pytest
from datetime import date, datetime, timezone as tz

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position


@pytest.fixture
def student(db) -> Student:
    """Create a standard test student."""
    return Student.objects.create(
        student_id="STU001",
        full_name="Alice Johnson",
        date_of_birth=date(2000, 5, 15),
        course="Computer Science",
        year=3,
    )


@pytest.fixture
def another_student(db) -> Student:
    """Create a second test student."""
    return Student.objects.create(
        student_id="STU002",
        full_name="Bob Williams",
        date_of_birth=date(1999, 8, 22),
        course="Mathematics",
        year=4,
    )


@pytest.fixture
def election(db) -> Election:
    """Create a test election in ACTIVE state."""
    return Election.objects.create(
        name="Test Election",
        start_time=datetime(2026, 1, 1, tzinfo=tz.utc),
        end_time=datetime(2026, 12, 31, tzinfo=tz.utc),
        status=Election.Status.ACTIVE,
    )


@pytest.fixture
def position(election) -> Position:
    """Create a test President position."""
    return Position.objects.create(
        election=election,
        title="President",
        category=Position.Category.EXECUTIVE,
        max_selections=1,
        order=1,
    )


@pytest.fixture
def candidate(position) -> Candidate:
    """Create a test candidate."""
    return Candidate.objects.create(
        position=position,
        full_name="Charlie Brown",
        party="Student Alliance",
    )


@pytest.fixture
def another_candidate(position) -> Candidate:
    """Create a second test candidate for the same position."""
    return Candidate.objects.create(
        position=position,
        full_name="Diana Ross",
        party="Student Union",
    )


@pytest.fixture
def vp_position(election) -> Position:
    """Create a VP position."""
    return Position.objects.create(
        election=election,
        title="Vice President",
        category=Position.Category.EXECUTIVE,
        max_selections=1,
        order=2,
    )


@pytest.fixture
def vp_candidate(vp_position) -> Candidate:
    """Create a VP candidate."""
    return Candidate.objects.create(
        position=vp_position,
        full_name="Eve Martinez",
        party="Student Alliance",
    )
