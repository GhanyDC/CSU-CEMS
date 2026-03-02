"""
Shared test configuration and fixtures.
"""
import pytest
from datetime import date

from apps.accounts.models import Student
from apps.elections.models import Candidate


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
def candidate(db) -> Candidate:
    """Create a test candidate."""
    return Candidate.objects.create(
        full_name="Charlie Brown",
        position="President",
        party="Student Alliance",
    )


@pytest.fixture
def another_candidate(db) -> Candidate:
    """Create a second test candidate for the same position."""
    return Candidate.objects.create(
        full_name="Diana Ross",
        position="President",
        party="Student Union",
    )


@pytest.fixture
def vp_candidate(db) -> Candidate:
    """Create a VP candidate."""
    return Candidate.objects.create(
        full_name="Eve Martinez",
        position="Vice President",
        party="Student Alliance",
    )
