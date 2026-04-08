"""
Tests for management commands.

Covers:
- import_students: CSV import with --dry-run, --update, error handling
- generate_pilot_data: data generation, --students, --clear flags
"""
import os
import tempfile
from datetime import date

import pytest
from django.core.management import call_command, CommandError

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.voting.models import Ballot, BallotSelection


# ── import_students ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestImportStudentsCommand:
    """Tests for the import_students management command."""

    def _write_csv(self, content):
        """Write CSV content to a temp file and return its path."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        return f.name

    def test_basic_import(self):
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "IMP001,Juan Dela Cruz,2002-05-15,College of Engineering,BSEE,3\n"
            "IMP002,Maria Santos,2001-08-22,College of Law,JD,1\n"
        )
        try:
            call_command("import_students", csv_path)
            assert Student.objects.filter(student_id="IMP001").exists()
            assert Student.objects.filter(student_id="IMP002").exists()
            assert Student.objects.count() == 2
        finally:
            os.unlink(csv_path)

    def test_dry_run_does_not_create(self):
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "DRY001,Test Student,2000-01-01,College of IT,BSIT,2\n"
        )
        try:
            call_command("import_students", csv_path, dry_run=True)
            assert not Student.objects.filter(student_id="DRY001").exists()
        finally:
            os.unlink(csv_path)

    def test_skip_existing_by_default(self):
        Student.objects.create(
            student_id="EXIST01",
            full_name="Original Name",
            date_of_birth=date(2000, 1, 1),
            course="CS",
            year=1,
        )
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "EXIST01,Updated Name,2000-01-01,College of IT,BSIT,2\n"
        )
        try:
            call_command("import_students", csv_path)
            s = Student.objects.get(student_id="EXIST01")
            assert s.full_name == "Original Name"  # Not updated
        finally:
            os.unlink(csv_path)

    def test_update_flag(self):
        Student.objects.create(
            student_id="UPD001",
            full_name="Old Name",
            date_of_birth=date(2000, 1, 1),
            course="CS",
            year=1,
        )
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "UPD001,New Name,2000-01-01,College of IT,BSIT,3\n"
        )
        try:
            call_command("import_students", csv_path, update=True)
            s = Student.objects.get(student_id="UPD001")
            assert s.full_name == "New Name"
            assert s.year == 3
        finally:
            os.unlink(csv_path)

    def test_file_not_found(self):
        with pytest.raises(CommandError, match="File not found"):
            call_command("import_students", "/nonexistent/path.csv")

    def test_missing_required_columns(self):
        csv_path = self._write_csv(
            "student_id,full_name\n"
            "COL001,Test\n"
        )
        try:
            with pytest.raises(CommandError, match="missing required columns"):
                call_command("import_students", csv_path)
        finally:
            os.unlink(csv_path)

    def test_invalid_date_format_logged_as_error(self):
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "BAD001,Bad Date,not-a-date,College of IT,BSIT,2\n"
            "GOOD01,Good Date,2000-01-01,College of IT,BSIT,2\n"
        )
        try:
            call_command("import_students", csv_path)
            assert not Student.objects.filter(student_id="BAD001").exists()
            assert Student.objects.filter(student_id="GOOD01").exists()
        finally:
            os.unlink(csv_path)

    def test_invalid_year_logged_as_error(self):
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            "YR001,Bad Year,2000-01-01,College of IT,BSIT,abc\n"
        )
        try:
            call_command("import_students", csv_path)
            assert not Student.objects.filter(student_id="YR001").exists()
        finally:
            os.unlink(csv_path)

    def test_missing_required_field_in_row(self):
        csv_path = self._write_csv(
            "student_id,full_name,date_of_birth,college,course,year\n"
            ",Missing ID,2000-01-01,College of IT,BSIT,2\n"
        )
        try:
            call_command("import_students", csv_path)
            assert Student.objects.count() == 0
        finally:
            os.unlink(csv_path)


# ── generate_pilot_data ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGeneratePilotDataCommand:
    """Tests for the generate_pilot_data management command."""

    def test_generates_students_and_election(self):
        call_command("generate_pilot_data", students=10)
        assert Student.objects.count() == 10
        assert Election.objects.count() == 1

    def test_creates_positions_and_candidates(self):
        call_command("generate_pilot_data", students=5)
        election = Election.objects.first()
        assert election is not None
        # Should have: 2 executive + 1 senate + 9 college reps + 1 party-list = 13
        assert Position.objects.filter(election=election).count() == 13
        assert Candidate.objects.filter(position__election=election).count() > 0

    def test_custom_student_count(self):
        call_command("generate_pilot_data", students=50)
        assert Student.objects.count() == 50

    def test_clear_flag(self):
        # Create some initial data
        Student.objects.create(
            student_id="PRE001", full_name="Preexisting",
            date_of_birth=date(2000, 1, 1), course="CS", year=1,
        )
        call_command("generate_pilot_data", students=5, clear=True)
        # Preexisting student should be cleared
        assert not Student.objects.filter(student_id="PRE001").exists()
        assert Student.objects.count() == 5

    def test_election_starts_as_draft(self):
        call_command("generate_pilot_data", students=5)
        election = Election.objects.first()
        assert election.status == Election.Status.DRAFT

    def test_clear_after_ballots_exist(self):
        """--clear must succeed even when ballots reference candidates/positions."""
        call_command("generate_pilot_data", students=5, clear=True)
        election = Election.objects.first()
        position = Position.objects.filter(election=election).first()
        candidate = Candidate.objects.filter(position=position).first()
        student = Student.objects.first()

        # Student is already on voter roll from generate_pilot_data; cast a ballot
        hashed = Ballot.hash_student_id(student.student_id, str(election.pk))
        ballot = Ballot.objects.create(
            election=election, hashed_student_id=hashed,
        )
        BallotSelection.objects.create(
            ballot=ballot, position=position, candidate=candidate,
        )

        # This previously raised ProtectedError
        call_command("generate_pilot_data", students=5, clear=True)

        # Verify clean slate
        assert Ballot.objects.count() == 0
        assert BallotSelection.objects.count() == 0
        assert Student.objects.count() == 5
        assert Election.objects.count() == 1

    def test_generate_clear_generate_repeatability(self):
        """Running generate → clear → generate must not raise errors."""
        call_command("generate_pilot_data", students=5, clear=True)
        assert Election.objects.count() == 1
        first_election_pk = Election.objects.first().pk

        call_command("generate_pilot_data", students=10, clear=True)
        assert Election.objects.count() == 1
        assert Student.objects.count() == 10
        # New election should have a different PK
        assert Election.objects.first().pk != first_election_pk

    def test_clear_removes_voter_roll(self):
        """--clear must remove EligibleVoter records along with everything else."""
        call_command("generate_pilot_data", students=5, clear=True)
        assert EligibleVoter.objects.count() > 0

        call_command("generate_pilot_data", students=5, clear=True)
        # New voter roll should exist for the new election only
        election = Election.objects.first()
        assert EligibleVoter.objects.filter(election=election).count() == 5
