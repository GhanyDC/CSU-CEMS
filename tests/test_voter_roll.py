"""
Tests for voter roll management (Bundle 02).

Covers:
- VoterRollService: import, matching, generate, finalize, counts
- EligibleVoter model constraints
- VerificationRecord model constraints
- Election type/college validation
- College election voter roll filtering
- import_verification management command
"""
import os
import tempfile
from datetime import date, datetime, timezone

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import IntegrityError

from apps.accounts.models import Student
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    VerificationRecord,
)
from apps.elections.services import (
    ElectionLifecycleService,
    ElectionNotReadyError,
    VoterRollError,
    VoterRollService,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_election(name="Test Election", status=Election.Status.DRAFT, **kwargs):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
        **kwargs,
    )


def make_student(student_id, college="", full_name=None):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name or f"Student {student_id}",
        date_of_birth=date(2001, 1, 1),
        college=college,
        course="Test",
        year=1,
    )


# ── Election type/college validation ─────────────────────────────────────────

@pytest.mark.django_db
class TestElectionTypeValidation:
    """Test Election election_type and college constraints."""

    def test_campus_election_default(self):
        e = make_election()
        assert e.election_type == Election.ElectionType.CAMPUS
        assert e.college == ""
        assert e.is_campus is True
        assert e.is_college is False

    def test_college_election_valid(self):
        college = OFFICIAL_COLLEGES[0]
        e = make_election(election_type=Election.ElectionType.COLLEGE, college=college)
        e.full_clean()
        assert e.is_college is True
        assert e.college == college

    def test_college_election_without_college_fails_clean(self):
        e = Election(
            name="Bad College",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            election_type=Election.ElectionType.COLLEGE,
            college="",
        )
        with pytest.raises(ValidationError, match="college"):
            e.full_clean()

    def test_college_election_unofficial_college_fails_clean(self):
        e = Election(
            name="Bad College",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            election_type=Election.ElectionType.COLLEGE,
            college="Fake College",
        )
        with pytest.raises(ValidationError, match="not a recognized"):
            e.full_clean()

    def test_campus_election_with_college_fails_clean(self):
        e = Election(
            name="Bad Campus",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            election_type=Election.ElectionType.CAMPUS,
            college="College of Nursing",
        )
        with pytest.raises(ValidationError, match="must not specify"):
            e.full_clean()

    def test_voter_roll_finalized_property(self):
        e = make_election()
        assert e.is_voter_roll_finalized is False
        from django.utils import timezone as tz
        e.voter_roll_finalized_at = tz.now()
        assert e.is_voter_roll_finalized is True


# ── EligibleVoter model ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEligibleVoterModel:
    """Test EligibleVoter constraints."""

    def test_create_eligible_voter(self):
        election = make_election()
        student = make_student("EV001", college="College of Nursing")
        ev = EligibleVoter.objects.create(
            election=election, student=student, college_snapshot="College of Nursing",
        )
        assert ev.pk is not None
        assert str(ev) == f"{student} – {election.name}"

    def test_unique_voter_per_election(self):
        election = make_election()
        student = make_student("EV002")
        EligibleVoter.objects.create(
            election=election, student=student, college_snapshot="",
        )
        with pytest.raises(IntegrityError):
            EligibleVoter.objects.create(
                election=election, student=student, college_snapshot="",
            )

    def test_same_student_different_elections(self):
        e1 = make_election(name="Election A")
        e2 = make_election(name="Election B")
        student = make_student("EV003")
        ev1 = EligibleVoter.objects.create(election=e1, student=student, college_snapshot="")
        ev2 = EligibleVoter.objects.create(election=e2, student=student, college_snapshot="")
        assert ev1.pk != ev2.pk


# ── VerificationRecord model ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestVerificationRecordModel:
    """Test VerificationRecord constraints."""

    def test_create_verification_record(self):
        election = make_election()
        vr = VerificationRecord.objects.create(
            election=election,
            student_id_input="VR001",
            full_name_input="Test Student",
            status=VerificationRecord.MatchStatus.PENDING,
        )
        assert "VR001" in str(vr)

    def test_unique_per_election(self):
        election = make_election()
        VerificationRecord.objects.create(
            election=election, student_id_input="DUP01",
        )
        with pytest.raises(IntegrityError):
            VerificationRecord.objects.create(
                election=election, student_id_input="DUP01",
            )

    def test_same_student_id_different_elections(self):
        e1 = make_election(name="Election A")
        e2 = make_election(name="Election B")
        vr1 = VerificationRecord.objects.create(election=e1, student_id_input="SAME01")
        vr2 = VerificationRecord.objects.create(election=e2, student_id_input="SAME01")
        assert vr1.pk != vr2.pk


# ── VoterRollService: import_verification ─────────────────────────────────────

@pytest.mark.django_db
class TestImportVerification:
    """Test VoterRollService.import_verification."""

    def test_basic_import_matched(self):
        election = make_election()
        make_student("IMP001", college="College of Nursing")
        rows = [{"student_id": "IMP001", "full_name": "Test", "college": "CoN"}]
        result = VoterRollService.import_verification(election, rows)
        assert result["created"] == 1
        assert result["matched"] == 1
        assert result["unmatched"] == 0
        vr = VerificationRecord.objects.get(election=election, student_id_input="IMP001")
        assert vr.status == VerificationRecord.MatchStatus.MATCHED
        assert vr.matched_student is not None

    def test_unmatched_record(self):
        election = make_election()
        rows = [{"student_id": "GHOST001"}]
        result = VoterRollService.import_verification(election, rows)
        assert result["unmatched"] == 1
        vr = VerificationRecord.objects.get(election=election, student_id_input="GHOST001")
        assert vr.status == VerificationRecord.MatchStatus.UNMATCHED
        assert vr.matched_student is None

    def test_duplicate_skipped(self):
        election = make_election()
        make_student("DUP001")
        VoterRollService.import_verification(election, [{"student_id": "DUP001"}])
        result = VoterRollService.import_verification(election, [{"student_id": "DUP001"}])
        assert result["skipped_duplicate"] == 1
        assert result["created"] == 0

    def test_mixed_import(self):
        election = make_election()
        make_student("MIX001")
        make_student("MIX002")
        rows = [
            {"student_id": "MIX001", "full_name": "A"},
            {"student_id": "MIX002", "full_name": "B"},
            {"student_id": "MIX003", "full_name": "C"},  # not in registrar
        ]
        result = VoterRollService.import_verification(election, rows)
        assert result["created"] == 3
        assert result["matched"] == 2
        assert result["unmatched"] == 1

    def test_import_after_finalization_rejected(self):
        election = make_election()
        s = make_student("FIN001")
        VoterRollService.import_verification(election, [{"student_id": "FIN001"}])
        VoterRollService.generate_voter_roll(election)
        VoterRollService.finalize_voter_roll(election, "admin")
        election.refresh_from_db()
        with pytest.raises(VoterRollError, match="already finalized"):
            VoterRollService.import_verification(election, [{"student_id": "NEW001"}])

    def test_empty_student_id_skipped(self):
        election = make_election()
        result = VoterRollService.import_verification(
            election, [{"student_id": ""}, {"student_id": "  "}]
        )
        assert result["created"] == 0


# ── VoterRollService: generate_voter_roll ─────────────────────────────────────

@pytest.mark.django_db
class TestGenerateVoterRoll:
    """Test VoterRollService.generate_voter_roll."""

    def test_basic_generation(self):
        election = make_election()
        s1 = make_student("GEN001", college="College of Nursing")
        s2 = make_student("GEN002", college="College of Nursing")
        VoterRollService.import_verification(election, [
            {"student_id": "GEN001"},
            {"student_id": "GEN002"},
        ])
        count = VoterRollService.generate_voter_roll(election)
        assert count == 2
        assert EligibleVoter.objects.filter(election=election).count() == 2

    def test_unmatched_not_included(self):
        election = make_election()
        make_student("GEN003")
        VoterRollService.import_verification(election, [
            {"student_id": "GEN003"},
            {"student_id": "GHOST"},
        ])
        count = VoterRollService.generate_voter_roll(election)
        assert count == 1

    def test_idempotent_generation(self):
        election = make_election()
        make_student("GEN004")
        VoterRollService.import_verification(election, [{"student_id": "GEN004"}])
        VoterRollService.generate_voter_roll(election)
        count = VoterRollService.generate_voter_roll(election)
        assert count == 0  # Already enrolled
        assert EligibleVoter.objects.filter(election=election).count() == 1

    def test_college_election_filters_by_college(self):
        college = OFFICIAL_COLLEGES[0]
        election = make_election(
            election_type=Election.ElectionType.COLLEGE, college=college,
        )
        s_in = make_student("COL001", college=college)
        s_out = make_student("COL002", college=OFFICIAL_COLLEGES[1])
        VoterRollService.import_verification(election, [
            {"student_id": "COL001"},
            {"student_id": "COL002"},
        ])
        count = VoterRollService.generate_voter_roll(election)
        assert count == 1
        assert EligibleVoter.objects.filter(election=election, student=s_in).exists()
        assert not EligibleVoter.objects.filter(election=election, student=s_out).exists()

    def test_college_snapshot_preserved(self):
        election = make_election()
        s = make_student("SNAP001", college="College of Nursing")
        VoterRollService.import_verification(election, [{"student_id": "SNAP001"}])
        VoterRollService.generate_voter_roll(election)
        ev = EligibleVoter.objects.get(election=election, student=s)
        assert ev.college_snapshot == "College of Nursing"

    def test_generate_after_finalization_rejected(self):
        election = make_election()
        s = make_student("FIN002")
        VoterRollService.import_verification(election, [{"student_id": "FIN002"}])
        VoterRollService.generate_voter_roll(election)
        VoterRollService.finalize_voter_roll(election, "admin")
        election.refresh_from_db()
        with pytest.raises(VoterRollError, match="already finalized"):
            VoterRollService.generate_voter_roll(election)


# ── VoterRollService: finalize_voter_roll ─────────────────────────────────────

@pytest.mark.django_db
class TestFinalizeVoterRoll:
    """Test VoterRollService.finalize_voter_roll."""

    def test_basic_finalization(self):
        election = make_election()
        s = make_student("FINAL001")
        VoterRollService.import_verification(election, [{"student_id": "FINAL001"}])
        VoterRollService.generate_voter_roll(election)
        VoterRollService.finalize_voter_roll(election, "eb_head")
        election.refresh_from_db()
        assert election.is_voter_roll_finalized is True
        assert election.voter_roll_finalized_by == "eb_head"

    def test_double_finalization_rejected(self):
        election = make_election()
        s = make_student("FINAL002")
        VoterRollService.import_verification(election, [{"student_id": "FINAL002"}])
        VoterRollService.generate_voter_roll(election)
        VoterRollService.finalize_voter_roll(election, "eb_head")
        with pytest.raises(VoterRollError, match="already finalized"):
            VoterRollService.finalize_voter_roll(election, "eb_head")

    def test_finalize_empty_roll_rejected(self):
        election = make_election()
        with pytest.raises(VoterRollError, match="empty voter roll"):
            VoterRollService.finalize_voter_roll(election, "admin")


# ── VoterRollService: counts ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestVoterRollCounts:
    """Test VoterRollService count methods."""

    def test_approved_count(self):
        election = make_election()
        for i in range(5):
            s = make_student(f"CNT{i:03d}")
            EligibleVoter.objects.create(election=election, student=s, college_snapshot="")
        assert VoterRollService.get_approved_count(election) == 5

    def test_approved_count_by_college(self):
        election = make_election()
        colleges = ["College of Nursing", "College of Nursing", OFFICIAL_COLLEGES[0]]
        for i, c in enumerate(colleges):
            s = make_student(f"CBC{i:03d}", college=c)
            EligibleVoter.objects.create(election=election, student=s, college_snapshot=c)
        result = VoterRollService.get_approved_count_by_college(election)
        assert result["College of Nursing"] == 2
        assert result[OFFICIAL_COLLEGES[0]] == 1

    def test_match_summary(self):
        election = make_election()
        make_student("SUM001")
        VoterRollService.import_verification(election, [
            {"student_id": "SUM001"},
            {"student_id": "GHOST_SUM"},
        ])
        summary = VoterRollService.get_match_summary(election)
        assert summary["total"] == 2
        assert summary["matched"] == 1
        assert summary["unmatched"] == 1

    def test_unmatched_records_queryset(self):
        election = make_election()
        make_student("UM001")
        VoterRollService.import_verification(election, [
            {"student_id": "UM001"},
            {"student_id": "UM_GHOST"},
        ])
        unmatched = VoterRollService.get_unmatched_records(election)
        assert unmatched.count() == 1
        assert unmatched.first().student_id_input == "UM_GHOST"


# ── import_verification management command ────────────────────────────────────

@pytest.mark.django_db
class TestImportVerificationCommand:
    """Test the import_verification management command."""

    def _write_csv(self, content):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        )
        f.write(content)
        f.close()
        return f.name

    def test_basic_import_command(self):
        election = make_election()
        make_student("CMD001")
        csv_path = self._write_csv(
            "student_id,full_name,college\n"
            "CMD001,Test Student,College of Nursing\n"
        )
        try:
            call_command("import_verification", str(election.pk), csv_path)
            assert VerificationRecord.objects.filter(
                election=election, student_id_input="CMD001"
            ).exists()
        finally:
            os.unlink(csv_path)

    def test_dry_run(self):
        election = make_election()
        make_student("DRY001")
        csv_path = self._write_csv(
            "student_id,full_name,college\n"
            "DRY001,Test,CoN\n"
        )
        try:
            call_command("import_verification", str(election.pk), csv_path, dry_run=True)
            assert not VerificationRecord.objects.filter(election=election).exists()
        finally:
            os.unlink(csv_path)

    def test_file_not_found(self):
        election = make_election()
        with pytest.raises(CommandError, match="File not found"):
            call_command("import_verification", str(election.pk), "/no/such/file.csv")

    def test_invalid_election_id(self):
        with pytest.raises(CommandError, match="Election not found"):
            call_command("import_verification", "bad-id", "dummy.csv")


# ── Position categories for college elections ─────────────────────────────────

@pytest.mark.django_db
class TestCollegePositionCategories:
    """Test that college election categories work correctly."""

    def test_college_executive_category_exists(self):
        assert Position.Category.COLLEGE_EXECUTIVE == "college_executive"

    def test_college_board_category_exists(self):
        assert Position.Category.COLLEGE_BOARD == "college_board"

    def test_college_executive_position_creation(self):
        college = OFFICIAL_COLLEGES[0]
        election = make_election(
            election_type=Election.ElectionType.COLLEGE, college=college,
        )
        pos = Position.objects.create(
            election=election,
            title="Governor",
            category=Position.Category.COLLEGE_EXECUTIVE,
            max_selections=1,
            order=1,
        )
        assert pos.category == "college_executive"


# ── Official colleges constant ────────────────────────────────────────────────

class TestOfficialColleges:
    """Test the OFFICIAL_COLLEGES constant."""

    def test_nine_colleges(self):
        assert len(OFFICIAL_COLLEGES) == 9

    def test_nursing_included(self):
        assert "College of Nursing" in OFFICIAL_COLLEGES

    def test_all_start_with_college_of(self):
        for college in OFFICIAL_COLLEGES:
            assert college.startswith("College of"), f"{college} does not start with 'College of'"
