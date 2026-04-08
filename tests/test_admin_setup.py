"""
Tests for admin election setup flow (Bundle 03).

Covers:
- ElectionSetupService: campus template, bulk college template
- CandidateManagementService: add/update/toggle in draft, blocked in non-draft
- ReadinessService: readiness check with pass/fail
- Admin setup API views: creation, detail, candidates, voter roll, readiness
- Role enforcement: Operator vs EB Head vs read-only roles
"""
import io
import json
from datetime import date, datetime, timezone

import pytest
from django.test import Client

from apps.accounts.models import AdminRole, Student
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    VerificationRecord,
)
from apps.elections.services import VoterRollService
from apps.elections.setup_services import (
    CandidateManagementService,
    ElectionSetupError,
    ElectionSetupService,
    ReadinessService,
)
from conftest import admin_client_for, create_admin_user, make_eligible, finalize_election_voter_roll


# ── Helpers ───────────────────────────────────────────────────────────────

DT_START = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
DT_END = datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc)


def make_student(student_id, college="", full_name=None):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name or f"Student {student_id}",
        date_of_birth=date(2001, 1, 1),
        college=college,
        course="Test",
        year=1,
    )


def make_draft_election(name="Test Election", **kwargs):
    return Election.objects.create(
        name=name,
        start_time=DT_START,
        end_time=DT_END,
        status=Election.Status.DRAFT,
        **kwargs,
    )


# ============================================================================
# Service-layer tests
# ============================================================================


@pytest.mark.django_db
class TestElectionSetupServiceCampus:
    """Test campus election creation from template."""

    def test_creates_campus_election(self):
        e = ElectionSetupService.create_campus_election("Test Campus", DT_START, DT_END)
        assert e.election_type == Election.ElectionType.CAMPUS
        assert e.status == Election.Status.DRAFT
        assert e.college == ""

    def test_campus_template_positions(self):
        e = ElectionSetupService.create_campus_election("Test Campus", DT_START, DT_END)
        positions = Position.objects.filter(election=e).order_by("order")

        # President, VP, Senator, 9 College Reps, Party-List = 13
        assert positions.count() == 13

        titles = [p.title for p in positions]
        assert "President" in titles
        assert "Vice President" in titles
        assert "Senator" in titles
        assert "Party-List Representative" in titles

        # Should have 9 college representative positions
        house_positions = [p for p in positions if p.category == Position.Category.HOUSE_COLLEGE]
        assert len(house_positions) == 9

    def test_campus_position_categories_correct(self):
        e = ElectionSetupService.create_campus_election("Test Campus", DT_START, DT_END)
        positions = {p.title: p for p in Position.objects.filter(election=e)}

        assert positions["President"].category == Position.Category.EXECUTIVE
        assert positions["President"].max_selections == 1
        assert positions["Vice President"].category == Position.Category.EXECUTIVE
        assert positions["Senator"].category == Position.Category.SENATE
        assert positions["Senator"].max_selections == 12
        assert positions["Party-List Representative"].category == Position.Category.HOUSE_PARTY
        assert positions["Party-List Representative"].max_selections == 3

    def test_empty_name_rejected(self):
        with pytest.raises(ElectionSetupError, match="name is required"):
            ElectionSetupService.create_campus_election("", DT_START, DT_END)

    def test_whitespace_name_rejected(self):
        with pytest.raises(ElectionSetupError, match="name is required"):
            ElectionSetupService.create_campus_election("   ", DT_START, DT_END)


@pytest.mark.django_db
class TestElectionSetupServiceCollege:
    """Test bulk college election creation from template."""

    def test_creates_nine_college_elections(self):
        elections = ElectionSetupService.create_college_elections("Test College", DT_START, DT_END)
        assert len(elections) == 9
        for e in elections:
            assert e.election_type == Election.ElectionType.COLLEGE
            assert e.status == Election.Status.DRAFT
            assert e.college in OFFICIAL_COLLEGES

    def test_college_template_positions(self):
        elections = ElectionSetupService.create_college_elections("Test College", DT_START, DT_END)
        for e in elections:
            positions = Position.objects.filter(election=e).order_by("order")
            assert positions.count() == 3

            titles = set(p.title for p in positions)
            assert titles == {"Governor", "Vice Governor", "Board Member"}

    def test_college_position_categories_correct(self):
        elections = ElectionSetupService.create_college_elections("Test College", DT_START, DT_END)
        e = elections[0]
        positions = {p.title: p for p in Position.objects.filter(election=e)}

        assert positions["Governor"].category == Position.Category.COLLEGE_EXECUTIVE
        assert positions["Governor"].max_selections == 1
        assert positions["Vice Governor"].category == Position.Category.COLLEGE_EXECUTIVE
        assert positions["Board Member"].category == Position.Category.COLLEGE_BOARD
        assert positions["Board Member"].max_selections == 8

    def test_naming_convention(self):
        elections = ElectionSetupService.create_college_elections("AY 2025-2026", DT_START, DT_END)
        names = set(e.name for e in elections)
        for college in OFFICIAL_COLLEGES:
            assert f"AY 2025-2026 – {college}" in names

    def test_subset_of_colleges(self):
        subset = [OFFICIAL_COLLEGES[0], OFFICIAL_COLLEGES[1]]
        elections = ElectionSetupService.create_college_elections("Test", DT_START, DT_END, subset)
        assert len(elections) == 2

    def test_invalid_college_rejected(self):
        with pytest.raises(ElectionSetupError, match="not a recognized"):
            ElectionSetupService.create_college_elections("Test", DT_START, DT_END, ["Fake College"])

    def test_empty_name_prefix_rejected(self):
        with pytest.raises(ElectionSetupError, match="name prefix is required"):
            ElectionSetupService.create_college_elections("", DT_START, DT_END)


@pytest.mark.django_db
class TestCandidateManagementService:
    """Test candidate management in draft elections."""

    def setup_method(self):
        self.election = make_draft_election()
        self.pos = Position.objects.create(
            election=self.election, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )

    def test_add_candidate(self):
        c = CandidateManagementService.add_candidate(self.pos, "Alice Smith", "Party A")
        assert c.full_name == "Alice Smith"
        assert c.party == "Party A"
        assert c.is_active is True

    def test_add_candidate_duplicate_rejected(self):
        CandidateManagementService.add_candidate(self.pos, "Alice Smith")
        with pytest.raises(ElectionSetupError, match="already exists"):
            CandidateManagementService.add_candidate(self.pos, "Alice Smith")

    def test_add_candidate_empty_name_rejected(self):
        with pytest.raises(ElectionSetupError, match="name is required"):
            CandidateManagementService.add_candidate(self.pos, "")

    def test_add_candidate_blocked_in_active(self):
        self.election.status = Election.Status.ACTIVE
        self.election.save()
        with pytest.raises(ElectionSetupError, match="Draft"):
            CandidateManagementService.add_candidate(self.pos, "Bob")

    def test_update_candidate_name(self):
        c = CandidateManagementService.add_candidate(self.pos, "Alice Smith")
        c = CandidateManagementService.update_candidate(c, full_name="Alice Johnson")
        assert c.full_name == "Alice Johnson"

    def test_update_candidate_party(self):
        c = CandidateManagementService.add_candidate(self.pos, "Alice Smith", "Party A")
        c = CandidateManagementService.update_candidate(c, party="Party B")
        assert c.party == "Party B"

    def test_toggle_candidate_active(self):
        c = CandidateManagementService.add_candidate(self.pos, "Alice Smith")
        assert c.is_active is True
        c = CandidateManagementService.update_candidate(c, is_active=False)
        assert c.is_active is False
        c = CandidateManagementService.update_candidate(c, is_active=True)
        assert c.is_active is True

    def test_update_blocked_in_active(self):
        c = CandidateManagementService.add_candidate(self.pos, "Alice Smith")
        self.election.status = Election.Status.ACTIVE
        self.election.save()
        with pytest.raises(ElectionSetupError, match="Draft"):
            CandidateManagementService.update_candidate(c, full_name="New Name")

    def test_update_name_uniqueness(self):
        CandidateManagementService.add_candidate(self.pos, "Alice")
        c = CandidateManagementService.add_candidate(self.pos, "Bob")
        with pytest.raises(ElectionSetupError, match="already exists"):
            CandidateManagementService.update_candidate(c, full_name="Alice")


@pytest.mark.django_db
class TestReadinessService:
    """Test election readiness checks."""

    def test_empty_election_not_ready(self):
        e = make_draft_election()
        # No positions created by default (we're using raw election, not template)
        report = ReadinessService.check_readiness(e)
        assert report["ready"] is False
        assert len(report["blocking_issues"]) > 0

    def test_fully_prepared_election_ready(self):
        e = ElectionSetupService.create_campus_election("Ready Test", DT_START, DT_END)

        # Add candidates to all positions
        for pos in Position.objects.filter(election=e):
            CandidateManagementService.add_candidate(pos, f"Candidate for {pos.title}")

        # Import verification and generate voter roll
        s = make_student("READY001")
        VoterRollService.import_verification(e, [{"student_id": "READY001"}])
        VoterRollService.generate_voter_roll(e)
        VoterRollService.finalize_voter_roll(e, "admin")
        e.refresh_from_db()

        report = ReadinessService.check_readiness(e)
        assert report["ready"] is True
        assert len(report["blocking_issues"]) == 0

    def test_missing_candidates_detected(self):
        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        # Only add candidate to first position
        first_pos = Position.objects.filter(election=e).order_by("order").first()
        CandidateManagementService.add_candidate(first_pos, "One Candidate")

        report = ReadinessService.check_readiness(e)
        assert report["ready"] is False
        assert any("no active candidates" in issue for issue in report["blocking_issues"])

    def test_unfinalized_voter_roll_detected(self):
        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        for pos in Position.objects.filter(election=e):
            CandidateManagementService.add_candidate(pos, f"C {pos.title}")

        s = make_student("VR001")
        VoterRollService.import_verification(e, [{"student_id": "VR001"}])
        VoterRollService.generate_voter_roll(e)
        # Don't finalize

        report = ReadinessService.check_readiness(e)
        assert report["ready"] is False
        assert any("finalized" in issue.lower() for issue in report["blocking_issues"])

    def test_active_election_not_ready(self):
        e = make_draft_election()
        e.status = Election.Status.ACTIVE
        e.save()
        report = ReadinessService.check_readiness(e)
        assert report["ready"] is False
        assert any("not in Draft" in issue for issue in report["blocking_issues"])


# ============================================================================
# API view tests
# ============================================================================


@pytest.mark.django_db
class TestListElectionsAPI:
    """Test GET /api/admin/elections/setup/list/"""

    def test_operator_can_list(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        make_draft_election("E1")
        make_draft_election("E2")

        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["elections"]) == 2

    def test_eb_head_can_list(self):
        user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 200

    def test_tally_watcher_can_list(self):
        user, _ = create_admin_user("tw", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 200

    def test_unauthenticated_rejected(self):
        client = Client(enforce_csrf_checks=False)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 401

    def test_technical_support_rejected(self):
        user, _ = create_admin_user("tech", role=AdminRole.TECHNICAL_SUPPORT)
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestElectionDetailAPI:
    """Test GET /api/admin/elections/setup/<id>/"""

    def test_returns_full_detail(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Detail Test", DT_START, DT_END)
        resp = client.get(f"/api/admin/elections/setup/{e.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["election"]["name"] == "Detail Test"
        assert len(data["election"]["positions"]) == 13
        assert "voter_roll_summary" in data["election"]

    def test_invalid_id_returns_404(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/00000000-0000-0000-0000-000000000000/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestCreateCampusElectionAPI:
    """Test POST /api/admin/elections/setup/create-campus/"""

    def test_operator_can_create_campus(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-campus/",
            data=json.dumps({
                "name": "Campus Election 2026",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert "13 positions" in data["message"]

        # Verify election was created
        e = Election.objects.get(pk=data["election"]["id"])
        assert e.name == "Campus Election 2026"
        assert e.election_type == Election.ElectionType.CAMPUS
        assert Position.objects.filter(election=e).count() == 13

    def test_eb_head_can_create_campus(self):
        user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-campus/",
            data=json.dumps({
                "name": "Campus Election 2026",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_missing_fields_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-campus/",
            data=json.dumps({"name": "Only Name"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_tally_watcher_cannot_create(self):
        user, _ = create_admin_user("tw", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-campus/",
            data=json.dumps({
                "name": "Denied",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestCreateCollegeElectionsAPI:
    """Test POST /api/admin/elections/setup/create-college/"""

    def test_operator_can_create_college_elections(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-college/",
            data=json.dumps({
                "name_prefix": "AY 2025-2026 College Election",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert len(data["elections"]) == 9

        # Verify each election
        for edata in data["elections"]:
            e = Election.objects.get(pk=edata["id"])
            assert e.election_type == Election.ElectionType.COLLEGE
            assert e.college in OFFICIAL_COLLEGES
            assert Position.objects.filter(election=e).count() == 3

    def test_missing_fields_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        resp = client.post(
            "/api/admin/elections/setup/create-college/",
            data=json.dumps({"name_prefix": "Only Prefix"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAddCandidateAPI:
    """Test POST /api/admin/elections/setup/<id>/candidates/add/"""

    def test_operator_can_add_candidate(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        pos = Position.objects.filter(election=e, title="President").first()

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/candidates/add/",
            data=json.dumps({
                "position_id": str(pos.pk),
                "full_name": "Juan Dela Cruz",
                "party": "Alyansa",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["candidate"]["full_name"] == "Juan Dela Cruz"

    def test_add_candidate_to_active_election_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        pos = Position.objects.filter(election=e, title="President").first()
        e.status = Election.Status.ACTIVE
        e.save()

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/candidates/add/",
            data=json.dumps({
                "position_id": str(pos.pk),
                "full_name": "Too Late",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Draft" in resp.json()["error"]

    def test_invalid_position_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/candidates/add/",
            data=json.dumps({
                "position_id": "00000000-0000-0000-0000-000000000000",
                "full_name": "Ghost",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestUpdateCandidateAPI:
    """Test POST /api/admin/elections/setup/<id>/candidates/<cid>/update/"""

    def test_operator_can_update_candidate(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        pos = Position.objects.filter(election=e, title="President").first()
        c = CandidateManagementService.add_candidate(pos, "Alice", "Party A")

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/candidates/{c.pk}/update/",
            data=json.dumps({"party": "Party B", "is_active": False}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate"]["party"] == "Party B"
        assert data["candidate"]["is_active"] is False

    def test_update_candidate_in_active_election_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Test", DT_START, DT_END)
        pos = Position.objects.filter(election=e, title="President").first()
        c = CandidateManagementService.add_candidate(pos, "Alice")
        e.status = Election.Status.ACTIVE
        e.save()

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/candidates/{c.pk}/update/",
            data=json.dumps({"party": "New Party"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestVoterRollImportAPI:
    """Test POST /api/admin/elections/setup/<id>/voter-roll/import/"""

    def test_operator_can_import_csv(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        make_student("CSV001", college="College of Nursing")

        csv_content = "student_id,full_name,college\nCSV001,Test Student,College of Nursing\nCSV002,Ghost,Unknown\n"
        csv_file = io.BytesIO(csv_content.encode("utf-8"))
        csv_file.name = "verification.csv"

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/import/",
            data={"csv_file": csv_file},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["summary"]["created"] == 2
        assert data["summary"]["matched"] == 1
        assert data["summary"]["unmatched"] == 1

    def test_no_file_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        resp = client.post(f"/api/admin/elections/setup/{e.pk}/voter-roll/import/")
        assert resp.status_code == 400

    def test_csv_without_student_id_column_rejected(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        csv_content = "name,college\nAlice,Nursing\n"
        csv_file = io.BytesIO(csv_content.encode("utf-8"))
        csv_file.name = "bad.csv"

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/import/",
            data={"csv_file": csv_file},
        )
        assert resp.status_code == 400
        assert "student_id" in resp.json()["error"]


@pytest.mark.django_db
class TestVoterRollSummaryAPI:
    """Test GET /api/admin/elections/setup/<id>/voter-roll/summary/"""

    def test_returns_summary(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        make_student("SUM001")
        VoterRollService.import_verification(e, [
            {"student_id": "SUM001"},
            {"student_id": "GHOST"},
        ])
        VoterRollService.generate_voter_roll(e)

        resp = client.get(f"/api/admin/elections/setup/{e.pk}/voter-roll/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["match_summary"]["matched"] == 1
        assert data["match_summary"]["unmatched"] == 1
        assert data["approved_count"] == 1
        assert data["unmatched_total"] == 1
        assert len(data["unmatched_records"]) == 1


@pytest.mark.django_db
class TestGenerateVoterRollAPI:
    """Test POST /api/admin/elections/setup/<id>/voter-roll/generate/"""

    def test_operator_can_generate(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        make_student("GEN001")
        VoterRollService.import_verification(e, [{"student_id": "GEN001"}])

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/generate/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["new_count"] == 1
        assert data["total_count"] == 1


@pytest.mark.django_db
class TestFinalizeVoterRollAPI:
    """Test POST /api/admin/elections/setup/<id>/voter-roll/finalize/"""

    def test_eb_head_can_finalize(self):
        user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)

        e = make_draft_election()
        s = make_student("FIN001")
        VoterRollService.import_verification(e, [{"student_id": "FIN001"}])
        VoterRollService.generate_voter_roll(e)

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/finalize/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["finalized_by"] == "Test EB Head"

        e.refresh_from_db()
        assert e.is_voter_roll_finalized is True

    def test_operator_cannot_finalize(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        s = make_student("FIN002")
        VoterRollService.import_verification(e, [{"student_id": "FIN002"}])
        VoterRollService.generate_voter_roll(e)

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/finalize/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_finalize_empty_roll_rejected(self):
        user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)

        e = make_draft_election()

        resp = client.post(
            f"/api/admin/elections/setup/{e.pk}/voter-roll/finalize/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["error"].lower()


@pytest.mark.django_db
class TestReadinessCheckAPI:
    """Test GET /api/admin/elections/setup/<id>/readiness/"""

    def test_returns_readiness_report(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = make_draft_election()
        Position.objects.create(
            election=e, title="President",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )

        resp = client.get(f"/api/admin/elections/setup/{e.pk}/readiness/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["ready"] is False
        assert len(data["checks"]) > 0
        assert len(data["blocking_issues"]) > 0

    def test_ready_election(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)

        e = ElectionSetupService.create_campus_election("Ready", DT_START, DT_END)
        for pos in Position.objects.filter(election=e):
            CandidateManagementService.add_candidate(pos, f"C {pos.title}")

        s = make_student("READY001")
        VoterRollService.import_verification(e, [{"student_id": "READY001"}])
        VoterRollService.generate_voter_roll(e)
        VoterRollService.finalize_voter_roll(e, "admin")
        e.refresh_from_db()

        resp = client.get(f"/api/admin/elections/setup/{e.pk}/readiness/")
        data = resp.json()
        assert data["ready"] is True
        assert len(data["blocking_issues"]) == 0


@pytest.mark.django_db
class TestRoleEnforcement:
    """Test that role enforcement is correct across all setup endpoints."""

    def setup_method(self):
        self.head_user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        self.op_user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        self.tw_user, _ = create_admin_user("tw", role=AdminRole.TALLY_WATCHER)
        self.audit_user, _ = create_admin_user("audit", role=AdminRole.AUDITOR)
        self.tech_user, _ = create_admin_user("tech", role=AdminRole.TECHNICAL_SUPPORT)

        self.head_client = admin_client_for(self.head_user)
        self.op_client = admin_client_for(self.op_user)
        self.tw_client = admin_client_for(self.tw_user)
        self.tech_client = admin_client_for(self.tech_user)

        self.election = make_draft_election()
        self.pos = Position.objects.create(
            election=self.election, title="Pres",
            category=Position.Category.EXECUTIVE, max_selections=1, order=1,
        )

    def test_create_campus_roles(self):
        body = json.dumps({"name": "T", "start_time": "2026-06-01T08:00:00Z", "end_time": "2026-06-03T17:00:00Z"})
        ct = "application/json"

        # EB Head and Operator can create
        assert self.head_client.post("/api/admin/elections/setup/create-campus/", data=body, content_type=ct).status_code == 201
        assert self.op_client.post("/api/admin/elections/setup/create-campus/", data=body, content_type=ct).status_code == 201

        # Tally watcher and tech support cannot
        assert self.tw_client.post("/api/admin/elections/setup/create-campus/", data=body, content_type=ct).status_code == 403
        assert self.tech_client.post("/api/admin/elections/setup/create-campus/", data=body, content_type=ct).status_code == 403

    def test_create_college_roles(self):
        body = json.dumps({"name_prefix": "T", "start_time": "2026-06-01T08:00:00Z", "end_time": "2026-06-03T17:00:00Z"})
        ct = "application/json"

        assert self.head_client.post("/api/admin/elections/setup/create-college/", data=body, content_type=ct).status_code == 201
        assert self.op_client.post("/api/admin/elections/setup/create-college/", data=body, content_type=ct).status_code == 201
        assert self.tw_client.post("/api/admin/elections/setup/create-college/", data=body, content_type=ct).status_code == 403

    def test_add_candidate_roles(self):
        body = json.dumps({"position_id": str(self.pos.pk), "full_name": "C1"})
        ct = "application/json"
        url = f"/api/admin/elections/setup/{self.election.pk}/candidates/add/"

        assert self.head_client.post(url, data=body, content_type=ct).status_code == 201
        body2 = json.dumps({"position_id": str(self.pos.pk), "full_name": "C2"})
        assert self.op_client.post(url, data=body2, content_type=ct).status_code == 201
        body3 = json.dumps({"position_id": str(self.pos.pk), "full_name": "C3"})
        assert self.tw_client.post(url, data=body3, content_type=ct).status_code == 403

    def test_finalize_voter_roll_roles(self):
        s = make_student("ROLE001")
        VoterRollService.import_verification(self.election, [{"student_id": "ROLE001"}])
        VoterRollService.generate_voter_roll(self.election)

        url = f"/api/admin/elections/setup/{self.election.pk}/voter-roll/finalize/"
        ct = "application/json"

        # Operator cannot finalize
        assert self.op_client.post(url, data="{}", content_type=ct).status_code == 403
        # Tally watcher cannot finalize
        assert self.tw_client.post(url, data="{}", content_type=ct).status_code == 403
        # EB Head can finalize
        assert self.head_client.post(url, data="{}", content_type=ct).status_code == 200

    def test_list_and_detail_read_access(self):
        # All non-tech roles can list
        assert self.head_client.get("/api/admin/elections/setup/list/").status_code == 200
        assert self.op_client.get("/api/admin/elections/setup/list/").status_code == 200
        assert self.tw_client.get("/api/admin/elections/setup/list/").status_code == 200
        assert self.tech_client.get("/api/admin/elections/setup/list/").status_code == 403

    def test_unauthenticated_access_denied(self):
        client = Client(enforce_csrf_checks=False)
        assert client.get("/api/admin/elections/setup/list/").status_code == 401
        assert client.post("/api/admin/elections/setup/create-campus/").status_code == 401


@pytest.mark.django_db
class TestAdminPanelPage:
    """Test the admin panel frontend page."""

    def test_admin_page_requires_auth(self):
        client = Client()
        resp = client.get("/admin-panel/")
        # Should redirect to admin login
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    def test_admin_page_renders_for_operator(self):
        user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get("/admin-panel/")
        assert resp.status_code == 200
        assert b"Election Management" in resp.content

    def test_admin_page_bootstraps_admin_context(self):
        user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get("/admin-panel/")
        assert resp.status_code == 200
        # The bootstrap_admin data should be in the page as JSON
        assert b"cems-bootstrap-admin" in resp.content
        assert b"Electoral Board Head" in resp.content


@pytest.mark.django_db
class TestCompleteSetupFlow:
    """Integration test: full election setup flow through the API."""

    def test_campus_election_full_setup(self):
        head_user, _ = create_admin_user("head", role=AdminRole.ELECTORAL_BOARD_HEAD)
        op_user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        head = admin_client_for(head_user)
        op = admin_client_for(op_user)

        # 1. Operator creates campus election
        resp = op.post(
            "/api/admin/elections/setup/create-campus/",
            data=json.dumps({
                "name": "SSC Election 2026",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        election_id = resp.json()["election"]["id"]

        # 2. Operator adds candidates
        e = Election.objects.get(pk=election_id)
        for pos in Position.objects.filter(election=e):
            resp = op.post(
                f"/api/admin/elections/setup/{election_id}/candidates/add/",
                data=json.dumps({
                    "position_id": str(pos.pk),
                    "full_name": f"Candidate for {pos.title}",
                    "party": "Test Party",
                }),
                content_type="application/json",
            )
            assert resp.status_code == 201

        # 3. Create test students and import verification CSV
        for i in range(5):
            make_student(f"FLOW{i:03d}", college=OFFICIAL_COLLEGES[i % 9])

        csv_content = "student_id,full_name,college\n"
        for i in range(5):
            csv_content += f"FLOW{i:03d},Student {i},{OFFICIAL_COLLEGES[i % 9]}\n"

        csv_file = io.BytesIO(csv_content.encode("utf-8"))
        csv_file.name = "verification.csv"
        resp = op.post(
            f"/api/admin/elections/setup/{election_id}/voter-roll/import/",
            data={"csv_file": csv_file},
        )
        assert resp.status_code == 200
        assert resp.json()["summary"]["matched"] == 5

        # 4. Operator generates voter roll
        resp = op.post(
            f"/api/admin/elections/setup/{election_id}/voter-roll/generate/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 5

        # 5. Operator checks readiness — not yet ready (voter roll not finalized)
        resp = op.get(f"/api/admin/elections/setup/{election_id}/readiness/")
        data = resp.json()
        assert data["ready"] is False

        # 6. Operator cannot finalize voter roll
        resp = op.post(
            f"/api/admin/elections/setup/{election_id}/voter-roll/finalize/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 403

        # 7. EB Head finalizes voter roll
        resp = head.post(
            f"/api/admin/elections/setup/{election_id}/voter-roll/finalize/",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 200

        # 8. Check readiness — now ready
        resp = op.get(f"/api/admin/elections/setup/{election_id}/readiness/")
        data = resp.json()
        assert data["ready"] is True

        # 9. EB Head starts election
        resp = head.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": election_id}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        # 10. Verify election is active
        e.refresh_from_db()
        assert e.status == Election.Status.ACTIVE

        # 11. Candidates cannot be modified in active election
        pos = Position.objects.filter(election=e).first()
        resp = op.post(
            f"/api/admin/elections/setup/{election_id}/candidates/add/",
            data=json.dumps({
                "position_id": str(pos.pk),
                "full_name": "Too Late",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_bulk_college_elections_setup(self):
        op_user, _ = create_admin_user("op", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        op = admin_client_for(op_user)

        # Create all 9 college elections at once
        resp = op.post(
            "/api/admin/elections/setup/create-college/",
            data=json.dumps({
                "name_prefix": "AY 2025-2026 College Election",
                "start_time": "2026-06-01T08:00:00Z",
                "end_time": "2026-06-03T17:00:00Z",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        elections = resp.json()["elections"]
        assert len(elections) == 9

        # Verify each election has correct structure
        for edata in elections:
            resp = op.get(f"/api/admin/elections/setup/{edata['id']}/")
            assert resp.status_code == 200
            detail = resp.json()["election"]
            assert detail["election_type"] == "college"
            assert len(detail["positions"]) == 3

            pos_titles = {p["title"] for p in detail["positions"]}
            assert pos_titles == {"Governor", "Vice Governor", "Board Member"}
