"""
Tests for model integrity and constraints.
"""
import pytest
from datetime import date

from django.db import IntegrityError

from apps.accounts.models import Student
from apps.elections.models import Candidate


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

    def test_has_voted_defaults_false(self) -> None:
        """New students default to has_voted=False."""
        s = Student.objects.create(
            student_id="DEF001",
            full_name="Default",
            date_of_birth=date(2000, 1, 1),
            course="Law",
            year=1,
        )
        assert s.has_voted is False

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


@pytest.mark.django_db
class TestCandidateModel:
    """Test Candidate model."""

    def test_candidate_creation(self) -> None:
        """Candidate can be created with required fields."""
        c = Candidate.objects.create(
            full_name="Test Candidate",
            position="Secretary",
        )
        assert c.is_active is True
        assert c.party == ""

    def test_str_representation(self) -> None:
        """__str__ includes name and position."""
        c = Candidate.objects.create(
            full_name="Named Candidate",
            position="Treasurer",
        )
        assert "Named Candidate" in str(c)
        assert "Treasurer" in str(c)
