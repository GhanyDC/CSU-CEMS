"""
Shared test configuration and fixtures.
"""
import pytest
from datetime import date, datetime, timezone as tz

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.elections.services import VoterRollService


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


# ---------------------------------------------------------------------------
# Voter roll helpers
# ---------------------------------------------------------------------------

def make_eligible(student: Student, election: Election) -> EligibleVoter:
    """Create an EligibleVoter record for a student in an election."""
    return EligibleVoter.objects.create(
        election=election,
        student=student,
        college_snapshot=student.college or "",
    )


def finalize_election_voter_roll(election: Election, finalized_by: str = "test") -> Election:
    """Finalize voter roll for an election (sets timestamp). Returns refreshed election."""
    election.voter_roll_finalized_at = timezone.now()
    election.voter_roll_finalized_by = finalized_by
    election.save(update_fields=["voter_roll_finalized_at", "voter_roll_finalized_by", "updated_at"])
    return election


# ---------------------------------------------------------------------------
# Admin auth fixtures (Bundle 01)
# ---------------------------------------------------------------------------

def create_admin_user(
    username="eb_head",
    password="securePass123!",
    role=AdminRole.ELECTORAL_BOARD_HEAD,
    display_name="Test EB Head",
):
    """Helper to create a Django User + AdminProfile. Returns (user, profile)."""
    user = User.objects.create_user(username=username, password=password)
    profile = AdminProfile.objects.create(
        user=user, role=role, display_name=display_name,
    )
    return user, profile


def admin_client_for(user):
    """Return a test Client authenticated as the given Django User."""
    client = Client(enforce_csrf_checks=False)
    client.force_login(user)
    return client


@pytest.fixture
def eb_head_user(db):
    """Create an Electoral Board Head admin user."""
    user, profile = create_admin_user(
        username="eb_head",
        role=AdminRole.ELECTORAL_BOARD_HEAD,
        display_name="VP Juan Dela Cruz",
    )
    return user, profile


@pytest.fixture
def operator_user(db):
    """Create an Electoral Board Operator admin user."""
    user, profile = create_admin_user(
        username="operator1",
        role=AdminRole.ELECTORAL_BOARD_OPERATOR,
        display_name="Operator One",
    )
    return user, profile


@pytest.fixture
def tally_watcher_user(db):
    """Create a Tally Watcher admin user."""
    user, profile = create_admin_user(
        username="tally1",
        role=AdminRole.TALLY_WATCHER,
        display_name="Tally Watcher One",
    )
    return user, profile
