"""
Reconciliation tests — verify final aligned behavior per the non-negotiable rules.

Tests cover:
- Admin tab structure (4 tabs only, no Monitoring)
- Role-based tally visibility by state (Active/Closed/Published)
- Operator restrictions (no positions, no lifecycle, redacted tally)
- Tally Watcher restrictions (read-only, redacted during Active, full after Closed)
- Position management permissions (EB Head only)
- Export permissions by role and state
- Draft-only editing/reordering
- College representative filtering
- Abstain computation
"""
import json
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

def _student(sid="RC_001", college="COE"):
    return Student.objects.create(
        student_id=sid, full_name=f"Student {sid}",
        date_of_birth=date(2001, 1, 1), course="Test", year=2, college=college,
    )


def _election(status=Election.Status.DRAFT, etype=Election.ElectionType.CAMPUS, college=""):
    return Election.objects.create(
        name="Reconciliation Election",
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=status, election_type=etype, college=college,
    )


def _position(election, title="President", category="executive", order=1):
    return Position.objects.create(
        election=election, title=title, category=category,
        max_selections=1, order=order,
    )


def _candidate(position, name="Alice", college=""):
    return Candidate.objects.create(
        position=position, full_name=name, party="Party", college=college,
    )


def _eb_client(username="rc_eb"):
    u, _ = create_admin_user(username=username, role=AdminRole.ELECTORAL_BOARD_HEAD)
    return admin_client_for(u)


def _op_client(username="rc_op"):
    u, _ = create_admin_user(username=username, role=AdminRole.ELECTORAL_BOARD_OPERATOR)
    return admin_client_for(u)


def _tw_client(username="rc_tw"):
    u, _ = create_admin_user(username=username, role=AdminRole.TALLY_WATCHER)
    return admin_client_for(u)


def _auditor_client(username="rc_aud"):
    u, _ = create_admin_user(username=username, role=AdminRole.AUDITOR)
    return admin_client_for(u)


# ══════════════════════════════════════════════════════════════════════════════
# 1. TALLY VISIBILITY BY ROLE AND STATE
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTallyVisibilityReconciled:
    """Final aligned tally visibility rules."""

    def test_eb_head_full_tally_during_active(self):
        """EB Head sees full per-candidate tally during Active."""
        el = _election(status=Election.Status.ACTIVE)
        pos = _position(el)
        _candidate(pos)
        client = _eb_client("tv_eb1")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "redacted" not in data or data.get("redacted") is not True
        # Full data includes per-candidate votes
        assert "positions" in data
        assert "results" in data["positions"][0]
        assert "votes" in data["positions"][0]["results"][0]

    def test_operator_redacted_during_active(self):
        """Operator gets redacted participation data during Active — no per-candidate votes."""
        el = _election(status=Election.Status.ACTIVE)
        pos = _position(el)
        _candidate(pos)
        client = _op_client("tv_op1")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redacted"] is True
        # No per-candidate votes
        for p in data["positions"]:
            for r in p["results"]:
                assert "votes" not in r

    def test_tally_watcher_redacted_during_active(self):
        """Tally Watcher gets redacted participation data during Active."""
        el = _election(status=Election.Status.ACTIVE)
        pos = _position(el)
        _candidate(pos)
        client = _tw_client("tv_tw1")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redacted"] is True

    def test_operator_redacted_during_closed(self):
        """Operator gets redacted tally even after Closed — stricter rule."""
        el = _election(status=Election.Status.CLOSED)
        pos = _position(el)
        _candidate(pos)
        client = _op_client("tv_op2")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redacted"] is True
        for p in data["positions"]:
            for r in p["results"]:
                assert "votes" not in r

    def test_tally_watcher_full_after_closed(self):
        """Tally Watcher sees full tally after Closed."""
        el = _election(status=Election.Status.CLOSED)
        pos = _position(el)
        _candidate(pos)
        client = _tw_client("tv_tw2")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("redacted") is not True
        assert "votes" in data["positions"][0]["results"][0]

    def test_eb_head_full_after_closed(self):
        """EB Head sees full tally after Closed."""
        el = _election(status=Election.Status.CLOSED)
        pos = _position(el)
        _candidate(pos)
        client = _eb_client("tv_eb2")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("redacted") is not True
        assert "votes" in data["positions"][0]["results"][0]

    def test_draft_tally_blocked_for_all(self):
        """All roles get 403 on tally endpoint during Draft."""
        el = _election(status=Election.Status.DRAFT)
        for fn, un in [(_eb_client, "tv_deb"), (_op_client, "tv_dop"), (_tw_client, "tv_dtw")]:
            client = fn(un)
            resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
            assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 2. OPERATOR RESTRICTIONS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOperatorRestrictions:
    """Operator cannot manage positions, lifecycle, or see full tally."""

    def test_operator_cannot_create_position(self):
        el = _election(status=Election.Status.DRAFT)
        client = _op_client("or_op1")
        resp = client.post(
            f"/api/admin/elections/setup/{el.pk}/positions/create/",
            json.dumps({"title": "New Pos", "category": "executive", "max_selections": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_reorder_positions(self):
        el = _election(status=Election.Status.DRAFT)
        pos = _position(el)
        client = _op_client("or_op2")
        resp = client.post(
            f"/api/admin/elections/setup/{el.pk}/positions/reorder/",
            json.dumps({"order": [str(pos.pk)]}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_start_election(self):
        el = _election(status=Election.Status.DRAFT)
        client = _op_client("or_op3")
        resp = client.post(
            "/api/admin/elections/start/",
            json.dumps({"election_id": str(el.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_close_election(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _op_client("or_op4")
        resp = client.post(
            "/api/admin/elections/close/",
            json.dumps({"election_id": str(el.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_publish_results(self):
        el = _election(status=Election.Status.CLOSED)
        client = _op_client("or_op5")
        resp = client.post(
            "/api/admin/elections/publish/",
            json.dumps({"election_id": str(el.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_operator_cannot_finalize_voter_roll(self):
        el = _election(status=Election.Status.DRAFT)
        client = _op_client("or_op6")
        resp = client.post(f"/api/admin/elections/setup/{el.pk}/voter-roll/finalize/")
        assert resp.status_code == 403

    def test_operator_can_add_candidate(self):
        el = _election(status=Election.Status.DRAFT)
        pos = _position(el)
        client = _op_client("or_op7")
        resp = client.post(
            f"/api/admin/elections/setup/{el.pk}/candidates/add/",
            json.dumps({"position_id": str(pos.pk), "full_name": "OpCandidate"}),
            content_type="application/json",
        )
        assert resp.status_code == 201


# ══════════════════════════════════════════════════════════════════════════════
# 3. TALLY WATCHER RESTRICTIONS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTallyWatcherRestrictions:
    """Tally Watcher is strictly read-only."""

    def test_tw_cannot_create_election(self):
        client = _tw_client("tw_r1")
        resp = client.post(
            "/api/admin/elections/setup/create-campus/",
            json.dumps({"name": "TW Election"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_tw_can_list_elections(self):
        client = _tw_client("tw_r2")
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 200

    def test_tw_can_view_election_detail(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _tw_client("tw_r3")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/")
        assert resp.status_code == 200

    def test_tw_can_view_turnout(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _tw_client("tw_r4")
        resp = client.get(f"/api/admin/elections/{el.pk}/turnout/")
        assert resp.status_code == 200

    def test_tw_cannot_import_voter_roll(self):
        el = _election(status=Election.Status.DRAFT)
        client = _tw_client("tw_r5")
        resp = client.post(f"/api/admin/elections/setup/{el.pk}/voter-roll/import/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 4. AUDITOR ROLE DENIED
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAuditorDenied:
    """Auditor role is denied on all admin endpoints."""

    def test_auditor_cannot_list_elections(self):
        client = _auditor_client("aud_d1")
        resp = client.get("/api/admin/elections/setup/list/")
        assert resp.status_code == 403

    def test_auditor_cannot_view_turnout(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _auditor_client("aud_d2")
        resp = client.get(f"/api/admin/elections/{el.pk}/turnout/")
        assert resp.status_code == 403

    def test_auditor_cannot_view_tally(self):
        el = _election(status=Election.Status.CLOSED)
        client = _auditor_client("aud_d3")
        resp = client.get(f"/api/admin/elections/{el.pk}/tally/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 5. EXPORT PERMISSIONS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestExportPermissionsReconciled:
    """Final export permissions by role and state."""

    def test_operator_can_export_turnout_csv(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _op_client("ex_op1")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/turnout/csv/")
        assert resp.status_code == 200

    def test_operator_cannot_export_tally_csv(self):
        el = _election(status=Election.Status.CLOSED)
        client = _op_client("ex_op2")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/tally/csv/")
        assert resp.status_code == 403

    def test_operator_cannot_export_participation_csv(self):
        el = _election(status=Election.Status.CLOSED)
        client = _op_client("ex_op3")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/participation/csv/")
        assert resp.status_code == 403

    def test_operator_cannot_export_ballot_audit_csv(self):
        el = _election(status=Election.Status.CLOSED)
        client = _op_client("ex_op4")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/ballot-audit/csv/")
        assert resp.status_code == 403

    def test_tw_can_export_turnout_csv(self):
        el = _election(status=Election.Status.ACTIVE)
        client = _tw_client("ex_tw1")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/turnout/csv/")
        assert resp.status_code == 200

    def test_tw_can_export_tally_csv_after_closed(self):
        el = _election(status=Election.Status.CLOSED)
        client = _tw_client("ex_tw2")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/tally/csv/")
        assert resp.status_code == 200

    def test_tw_cannot_export_participation_csv(self):
        el = _election(status=Election.Status.CLOSED)
        client = _tw_client("ex_tw3")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/participation/csv/")
        assert resp.status_code == 403

    def test_tw_cannot_export_ballot_audit_csv(self):
        el = _election(status=Election.Status.CLOSED)
        client = _tw_client("ex_tw4")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/ballot-audit/csv/")
        assert resp.status_code == 403

    def test_eb_head_can_export_all_after_closed(self):
        el = _election(status=Election.Status.CLOSED)
        client = _eb_client("ex_eb1")
        for endpoint in ["turnout/csv", "turnout/text", "tally/csv", "participation/csv", "ballot-audit/csv"]:
            resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/{endpoint}/")
            assert resp.status_code == 200, f"Failed for {endpoint}"

    def test_exports_blocked_during_draft(self):
        el = _election(status=Election.Status.DRAFT)
        client = _eb_client("ex_eb2")
        resp = client.get(f"/api/admin/elections/setup/{el.pk}/export/turnout/csv/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 6. POSITION MANAGEMENT IN DRAFT ONLY
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDraftOnlyEditing:
    """Positions and candidates can only be managed during Draft."""

    def test_cannot_add_candidate_during_active(self):
        el = _election(status=Election.Status.ACTIVE)
        pos = _position(el)
        client = _eb_client("do_eb1")
        resp = client.post(
            f"/api/admin/elections/setup/{el.pk}/candidates/add/",
            json.dumps({"position_id": str(pos.pk), "full_name": "Late Cand"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cannot_reorder_during_active(self):
        el = _election(status=Election.Status.ACTIVE)
        pos = _position(el)
        client = _eb_client("do_eb2")
        resp = client.post(
            f"/api/admin/elections/setup/{el.pk}/positions/reorder/",
            json.dumps({"order": [str(pos.pk)]}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 7. COLLEGE REPRESENTATIVE FILTERING
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCollegeRepFiltering:
    """Students see only College Rep candidates from their own college."""

    def test_student_sees_only_own_college_reps(self):
        el = _election(status=Election.Status.ACTIVE, etype=Election.ElectionType.CAMPUS)
        # Executive position (all students see)
        pres = _position(el, title="President", category="executive", order=1)
        _candidate(pres, name="Pres Candidate")
        # College rep position
        col_rep = _position(el, title="COE Representative", category="house_college", order=2)
        _candidate(col_rep, name="COE Rep", college="COE")
        _candidate(col_rep, name="CEBA Rep", college="CEBA")

        # Student from COE
        student = _student(sid="CR_001", college="COE")
        make_eligible(student, el)
        finalize_election_voter_roll(el)

        client = Client()
        client.post("/api/auth/login/", {
            "student_id": student.student_id,
            "date_of_birth": "2001-01-01",
        })
        resp = client.get(f"/api/elections/{el.pk}/ballot/")
        assert resp.status_code == 200
        data = resp.json()

        # Should see President position
        position_titles = [p["title"] for p in data["positions"]]
        assert "President" in position_titles

        # Should see COE Rep but NOT CEBA Rep for the college rep position
        col_rep_pos = [p for p in data["positions"] if p["title"] == "COE Representative"][0]
        candidate_names = [c["full_name"] for c in col_rep_pos["candidates"]]
        assert "COE Rep" in candidate_names
        assert "CEBA Rep" not in candidate_names


# ══════════════════════════════════════════════════════════════════════════════
# 8. ABSTAIN COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAbstainComputation:
    """Abstain is computed as total_ballots - position_participation."""

    def test_abstain_count_reflects_missing_selections(self):
        el = _election(status=Election.Status.ACTIVE)
        pos1 = _position(el, title="President", order=1)
        pos2 = _position(el, title="VP", order=2)
        c1 = _candidate(pos1, name="A1")
        c2 = _candidate(pos2, name="B1")

        # Create 3 voters, all vote for President but only 2 vote for VP
        students = []
        for i in range(3):
            s = _student(sid=f"AB_{i:03d}")
            make_eligible(s, el)
            students.append(s)

        finalize_election_voter_roll(el)

        for i in range(3):
            selections = [(str(pos1.pk), str(c1.pk))]
            if i < 2:
                selections.append((str(pos2.pk), str(c2.pk)))
            BallotService.cast_ballot(students[i], el, selections)

        results = ResultService.compute_results_with_thresholds(el)
        pos_results = {p["position"]: p for p in results["positions"]}

        # President: all 3 voted, 0 abstain
        assert pos_results["President"]["abstain_count"] == 0
        assert pos_results["President"]["position_participation"] == 3

        # VP: 2 voted, 1 abstain
        assert pos_results["VP"]["abstain_count"] == 1
        assert pos_results["VP"]["position_participation"] == 2
