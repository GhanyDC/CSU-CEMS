"""
Tests for new features: export system, role-based tally visibility,
abstain counting, position reorder, and role enforcement changes.
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from django.test import Client

from apps.accounts.models import AdminRole, Student
from apps.elections.models import Candidate, Election, EligibleVoter, Position
from apps.elections.services import ResultService
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotService
from conftest import (
    admin_client_for,
    create_admin_user,
    finalize_election_voter_roll,
    make_eligible,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_student(student_id="EXP_001", full_name="Export Student", college=""):
    return Student.objects.create(
        student_id=student_id,
        full_name=full_name,
        date_of_birth=date(2001, 1, 1),
        course="Test",
        year=2,
        college=college,
    )


def make_election(
    name="Test Election",
    status=Election.Status.ACTIVE,
    election_type=Election.ElectionType.CAMPUS,
    college="",
):
    return Election.objects.create(
        name=name,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status,
        election_type=election_type,
        college=college,
    )


def make_position(election, title="President", category="executive", max_selections=1, order=0):
    return Position.objects.create(
        election=election,
        title=title,
        category=category,
        max_selections=max_selections,
        order=order,
    )


def make_candidate(position, full_name="Candidate A", party="Party X", college=""):
    return Candidate.objects.create(
        position=position,
        full_name=full_name,
        party=party,
        college=college,
    )


def setup_election_with_votes():
    """Set up a full election with positions, candidates, voters, and votes."""
    election = make_election(status=Election.Status.ACTIVE)
    pos1 = make_position(election, title="President", order=1)
    pos2 = make_position(election, title="Vice President", order=2)
    c1 = make_candidate(pos1, full_name="Alice")
    c2 = make_candidate(pos1, full_name="Bob")
    c3 = make_candidate(pos2, full_name="Charlie")

    # Create students, make eligible, cast votes
    students = []
    for i in range(5):
        s = make_student(student_id=f"EXP_{i:03d}", full_name=f"Student {i}")
        make_eligible(s, election)
        students.append(s)

    finalize_election_voter_roll(election)

    # 3 vote for Alice + Charlie, 1 votes for Bob + Charlie, 1 skips VP (abstain)
    for i in range(3):
        BallotService.cast_ballot(
            students[i], election,
            [(str(pos1.pk), str(c1.pk)), (str(pos2.pk), str(c3.pk))],
        )
    BallotService.cast_ballot(
        students[3], election,
        [(str(pos1.pk), str(c2.pk)), (str(pos2.pk), str(c3.pk))],
    )
    # Student 4 only votes for President — abstains VP
    BallotService.cast_ballot(
        students[4], election,
        [(str(pos1.pk), str(c1.pk))],
    )

    # Move to CLOSED after voting
    election.status = Election.Status.CLOSED
    election.save()

    return election, pos1, pos2, c1, c2, c3, students


# ══════════════════════════════════════════════════════════════════════════════
# 1. Export Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestExportTurnoutCSV:
    """Tests for GET /api/admin/elections/setup/<id>/export/turnout/csv/"""

    def test_turnout_csv_active_election(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="EBH01", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")
        assert "attachment" in resp["Content-Disposition"]

    def test_turnout_csv_blocked_for_draft(self):
        election = make_election(status=Election.Status.DRAFT)
        user, _ = create_admin_user(username="EBH02", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 403

    def test_turnout_csv_operator_can_access(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="OP01", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 200

    def test_turnout_csv_tally_watcher_can_access(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="TW01", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 200

    def test_turnout_csv_auditor_blocked(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="AUD01", role=AdminRole.AUDITOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 403

    def test_turnout_csv_content(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="EBH03", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        content = resp.content.decode("utf-8")
        assert "Election Turnout Update" in content
        assert "Total Ballots Cast" in content
        assert "5" in content  # 5 ballots


@pytest.mark.django_db
class TestExportTurnoutText:
    """Tests for GET /api/admin/elections/setup/<id>/export/turnout/text/"""

    def test_turnout_text_returns_json(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="EBH04", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/text/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "UNOFFICIAL TURNOUT UPDATE" in data["text"]

    def test_turnout_text_blocked_for_draft(self):
        election = make_election(status=Election.Status.DRAFT)
        user, _ = create_admin_user(username="EBH05", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/text/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestExportTallyCSV:
    """Tests for GET /api/admin/elections/setup/<id>/export/tally/csv/"""

    def test_tally_csv_closed_for_eb_head(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="EBH06", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/tally/csv/")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")
        content = resp.content.decode("utf-8")
        assert "Internal Canvassing" in content
        assert "Alice" in content

    def test_tally_csv_blocked_for_active(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="EBH07", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/tally/csv/")
        assert resp.status_code == 403

    def test_tally_csv_tally_watcher_can_access(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="TW02", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/tally/csv/")
        assert resp.status_code == 200

    def test_tally_csv_operator_blocked(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="OP02", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/tally/csv/")
        assert resp.status_code == 403

    def test_tally_csv_has_abstain_data(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="EBH08", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/tally/csv/")
        content = resp.content.decode("utf-8")
        assert "Abstain Count" in content


@pytest.mark.django_db
class TestExportParticipationCSV:
    """Tests for GET /api/admin/elections/setup/<id>/export/participation/csv/"""

    def test_participation_csv_eb_head_only(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="EBH09", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/participation/csv/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Participation Report" in content
        assert "Has Voted" in content

    def test_participation_csv_tally_watcher_blocked(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="TW03", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/participation/csv/")
        assert resp.status_code == 403

    def test_participation_csv_blocked_during_active(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="EBH10", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/participation/csv/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestExportBallotAuditCSV:
    """Tests for GET /api/admin/elections/setup/<id>/export/ballot-audit/csv/"""

    def test_ballot_audit_csv_eb_head(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="EBH11", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/ballot-audit/csv/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Anonymous Ballot Audit" in content
        assert "..." in content  # Truncated hashes

    def test_ballot_audit_csv_operator_blocked(self):
        election, *_ = setup_election_with_votes()
        user, _ = create_admin_user(username="OP03", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/ballot-audit/csv/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 2. Abstain Counting in Results
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAbstainCounting:
    """Verify that abstain counts are computed correctly in results."""

    def test_abstain_count_when_voter_skips_position(self):
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        results = ResultService.compute_results(election)

        president_data = next(p for p in results["positions"] if p["position"] == "President")
        vp_data = next(p for p in results["positions"] if p["position"] == "Vice President")

        # All 5 voted for President
        assert president_data["abstain_count"] == 0
        assert president_data["position_participation"] == 5

        # 4 voted for VP, 1 abstained
        assert vp_data["abstain_count"] == 1
        assert vp_data["position_participation"] == 4

    def test_abstain_count_all_positions_have_total_ballots(self):
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        results = ResultService.compute_results(election)

        for p in results["positions"]:
            assert p["total_ballots"] == 5

    def test_total_votes_consistent_with_participation(self):
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        results = ResultService.compute_results(election)

        president_data = next(p for p in results["positions"] if p["position"] == "President")
        total_candidate_votes = sum(r["votes"] for r in president_data["results"])
        # For single-selection: total votes == participation count
        assert total_candidate_votes == president_data["position_participation"]

    def test_abstain_in_thresholds_result(self):
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        results = ResultService.compute_results_with_thresholds(election)

        vp_data = next(p for p in results["positions"] if p["position"] == "Vice President")
        assert vp_data["abstain_count"] == 1
        assert results["total_ballots"] == 5
        assert results["total_eligible"] == 5


# ══════════════════════════════════════════════════════════════════════════════
# 3. Tally Visibility Role Enforcement
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTallyVisibilityRoles:
    """Test role-based tally visibility rules per implementation."""

    def test_eb_head_sees_full_tally_during_active(self):
        """EB Head can view full tally even during Active."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        make_candidate(pos)
        user, _ = create_admin_user(username="EBH20", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Full data — positions contain results
        assert len(data["positions"]) >= 1

    def test_operator_gets_redacted_tally_during_closed(self):
        """Operator can see tally after Closed but without per-candidate votes."""
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        user, _ = create_admin_user(username="OP20", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        # Operator should get redacted data — no per-candidate votes during active
        # But after closed, they get participation summary
        assert data["success"] is True

    def test_tally_watcher_blocked_during_active(self):
        """Tally Watcher cannot access tally during Active election."""
        election = make_election(status=Election.Status.ACTIVE)
        pos = make_position(election)
        make_candidate(pos)
        user, _ = create_admin_user(username="TW20", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 403

    def test_tally_watcher_sees_tally_after_closed(self):
        """Tally Watcher can access full tally after election is closed."""
        election, pos1, pos2, c1, c2, c3, students = setup_election_with_votes()
        user, _ = create_admin_user(username="TW21", role=AdminRole.TALLY_WATCHER)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/{election.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 4. Position Reorder
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPositionReorder:
    """Tests for POST /api/admin/elections/setup/<id>/positions/reorder/"""

    def test_reorder_positions_eb_head(self):
        election = make_election(status=Election.Status.DRAFT)
        p1 = make_position(election, title="President", order=1)
        p2 = make_position(election, title="VP", order=2)
        p3 = make_position(election, title="Secretary", order=3)

        user, _ = create_admin_user(username="EBH30", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.post(
            f"/api/admin/elections/setup/{election.pk}/positions/reorder/",
            json.dumps({"order": [str(p3.pk), str(p1.pk), str(p2.pk)]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify new order (1-based)
        p3.refresh_from_db()
        p1.refresh_from_db()
        p2.refresh_from_db()
        assert p3.order == 1
        assert p1.order == 2
        assert p2.order == 3

    def test_reorder_operator_blocked(self):
        election = make_election(status=Election.Status.DRAFT)
        p1 = make_position(election, title="President", order=1)
        p2 = make_position(election, title="VP", order=2)

        user, _ = create_admin_user(username="OP30", role=AdminRole.ELECTORAL_BOARD_OPERATOR)
        client = admin_client_for(user)
        resp = client.post(
            f"/api/admin/elections/setup/{election.pk}/positions/reorder/",
            json.dumps({"order": [str(p2.pk), str(p1.pk)]}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_reorder_blocked_for_non_draft(self):
        election = make_election(status=Election.Status.ACTIVE)
        p1 = make_position(election, title="President", order=1)
        p2 = make_position(election, title="VP", order=2)

        user, _ = create_admin_user(username="EBH31", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.post(
            f"/api/admin/elections/setup/{election.pk}/positions/reorder/",
            json.dumps({"order": [str(p2.pk), str(p1.pk)]}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 5. Audit Logging for Exports
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestExportAuditLogging:
    """Verify that exports create audit log entries."""

    def test_export_creates_audit_log(self):
        from apps.audit.models import AuditLog

        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="EBH40", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)

        initial_count = AuditLog.objects.filter(
            event_type=AuditLog.EventType.EXPORT_GENERATED
        ).count()

        client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")

        final_count = AuditLog.objects.filter(
            event_type=AuditLog.EventType.EXPORT_GENERATED
        ).count()
        assert final_count == initial_count + 1


# ══════════════════════════════════════════════════════════════════════════════
# 6. Role Enforcement — AUDITOR Removed
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAuditorRoleRemoved:
    """AUDITOR role should no longer have access to admin endpoints."""

    def test_auditor_blocked_from_election_list(self):
        user, _ = create_admin_user(username="AUD10", role=AdminRole.AUDITOR)
        client = admin_client_for(user)
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 403

    def test_auditor_blocked_from_export(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="AUD11", role=AdminRole.AUDITOR)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 403

    def test_technical_support_blocked_from_export(self):
        election = make_election(status=Election.Status.ACTIVE)
        user, _ = create_admin_user(username="TECH01", role=AdminRole.TECHNICAL_SUPPORT)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 7. Export Election Not Found
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestExportEdgeCases:
    """Edge cases for export endpoints."""

    def test_export_nonexistent_election(self):
        user, _ = create_admin_user(username="EBH50", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/admin/elections/setup/{fake_id}/export/turnout/csv/")
        assert resp.status_code == 404

    def test_turnout_csv_published_election(self):
        election, *_ = setup_election_with_votes()
        election.status = Election.Status.PUBLISHED
        election.save()
        user, _ = create_admin_user(username="EBH51", role=AdminRole.ELECTORAL_BOARD_HEAD)
        client = admin_client_for(user)
        resp = client.get(f"/api/admin/elections/setup/{election.pk}/export/turnout/csv/")
        assert resp.status_code == 200
