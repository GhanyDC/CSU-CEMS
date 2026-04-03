"""
End-to-end integration tests for the full voting workflow.

Tests the complete flow: login → view election → cast ballot → check status
→ admin lifecycle → view results.
"""
import json
from datetime import date, datetime, timezone

import pytest
from django.test import Client

from apps.accounts.models import Student
from apps.audit.models import AuditLog
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import Ballot


def make_student(student_id, dob="2000-01-01", is_admin=False):
    return Student.objects.create(
        student_id=student_id,
        full_name=f"Student {student_id}",
        date_of_birth=date.fromisoformat(dob),
        course="Test",
        year=1,
        is_admin=is_admin,
    )


@pytest.mark.django_db
class TestFullVotingWorkflow:
    """End-to-end test: login → vote → close → publish → results."""

    def test_complete_election_flow(self):
        # 1. Setup: admin, voter, election with positions/candidates
        admin = make_student("ADMIN001", is_admin=True)
        voter = make_student("VOTER001", dob="2001-06-15")

        election = Election.objects.create(
            name="Integration Test Election",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=Election.Status.DRAFT,
        )
        pres = Position.objects.create(
            election=election, title="President",
            category="executive", max_selections=1, order=1,
        )
        cand_a = Candidate.objects.create(
            position=pres, full_name="Alice", party="Alpha",
        )
        cand_b = Candidate.objects.create(
            position=pres, full_name="Bob", party="Beta",
        )

        client = Client(enforce_csrf_checks=False)

        # 2. Admin login
        resp = client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "ADMIN001", "date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        # 3. Admin starts election (DRAFT → ACTIVE)
        resp = client.post(
            "/api/admin/elections/start/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        # 4. Voter login (new session)
        voter_client = Client(enforce_csrf_checks=False)
        resp = voter_client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "VOTER001", "date_of_birth": "2001-06-15"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        # 5. Voter views current election
        resp = voter_client.get("/api/elections/current/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["election"]["name"] == "Integration Test Election"
        assert len(data["election"]["positions"]) == 1
        assert len(data["election"]["positions"][0]["candidates"]) == 2

        # 6. Voter checks status (hasn't voted yet)
        resp = voter_client.get("/api/elections/status/")
        assert resp.status_code == 200
        assert resp.json()["has_voted"] is False

        # 7. Voter casts ballot for Alice
        resp = voter_client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [
                    {"position_id": str(pres.pk), "candidate_id": str(cand_a.pk)}
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["success"] is True

        # 8. Voter checks status (has voted)
        resp = voter_client.get("/api/elections/status/")
        assert resp.json()["has_voted"] is True

        # 9. Voter tries to vote again → 409
        resp = voter_client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [
                    {"position_id": str(pres.pk), "candidate_id": str(cand_b.pk)}
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 409

        # 10. Results not available yet
        resp = voter_client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 403

        # 11. Admin closes election
        resp = client.post(
            "/api/admin/elections/close/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"

        # 12. Voter tries to vote in closed election → 409
        voter2 = make_student("VOTER002", dob="2002-03-10")
        v2_client = Client(enforce_csrf_checks=False)
        v2_client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "VOTER002", "date_of_birth": "2002-03-10"}),
            content_type="application/json",
        )
        resp = v2_client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [
                    {"position_id": str(pres.pk), "candidate_id": str(cand_a.pk)}
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 409

        # 13. Admin publishes results
        resp = client.post(
            "/api/admin/elections/publish/",
            data=json.dumps({"election_id": str(election.pk)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        # 14. Voter views results
        resp = voter_client.get(f"/api/elections/results/{election.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["election_name"] == "Integration Test Election"
        assert len(data["positions"]) == 1
        pos_result = data["positions"][0]
        assert pos_result["total_votes"] == 1
        assert pos_result["winner"] == "Alice"

        # 15. Verify audit trail
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.ELECTION_STARTED
        ).exists()
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.VOTE_CAST
        ).exists()
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.ELECTION_CLOSED
        ).exists()
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.RESULTS_PUBLISHED
        ).exists()
        assert AuditLog.objects.filter(
            event_type=AuditLog.EventType.SUSPICIOUS_ACTIVITY
        ).exists()  # From duplicate ballot attempt


@pytest.mark.django_db
class TestMultiPositionBallotIntegration:
    """Test voting with multiple positions via HTTP endpoints."""

    def test_multi_position_ballot_via_api(self):
        student = make_student("MULTI001")
        election = Election.objects.create(
            name="Multi-Position Election",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=Election.Status.ACTIVE,
        )
        pres = Position.objects.create(
            election=election, title="President",
            category="executive", max_selections=1, order=1,
        )
        senate = Position.objects.create(
            election=election, title="Senator",
            category="senate", max_selections=2, order=2,
        )
        pres_cand = Candidate.objects.create(
            position=pres, full_name="Pres Cand", party="A",
        )
        sen_a = Candidate.objects.create(
            position=senate, full_name="Sen A", party="B",
        )
        sen_b = Candidate.objects.create(
            position=senate, full_name="Sen B", party="C",
        )

        client = Client(enforce_csrf_checks=False)
        client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "MULTI001", "date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )

        resp = client.post(
            "/api/voting/cast/",
            data=json.dumps({
                "election_id": str(election.pk),
                "selections": [
                    {"position_id": str(pres.pk), "candidate_id": str(pres_cand.pk)},
                    {"position_id": str(senate.pk), "candidate_id": str(sen_a.pk)},
                    {"position_id": str(senate.pk), "candidate_id": str(sen_b.pk)},
                ],
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        ballot_id = resp.json()["ballot_id"]
        ballot = Ballot.objects.get(pk=ballot_id)
        assert ballot.selections.count() == 3


@pytest.mark.django_db
class TestSecurityIntegration:
    """Test security-related integration scenarios."""

    def test_non_admin_cannot_manipulate_election(self):
        """Regular student cannot start/close/publish elections."""
        student = make_student("SEC001")
        election = Election.objects.create(
            name="Security Test",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=Election.Status.DRAFT,
        )

        client = Client(enforce_csrf_checks=False)
        client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "SEC001", "date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )

        for url in [
            "/api/admin/elections/start/",
            "/api/admin/elections/close/",
            "/api/admin/elections/publish/",
        ]:
            resp = client.post(
                url,
                data=json.dumps({"election_id": str(election.pk)}),
                content_type="application/json",
            )
            assert resp.status_code == 403, f"Expected 403 for {url}"

        # Election should still be DRAFT
        election.refresh_from_db()
        assert election.status == Election.Status.DRAFT

    def test_unauthenticated_cannot_access_any_endpoint(self):
        """All protected endpoints return 401 without authentication."""
        client = Client(enforce_csrf_checks=False)
        endpoints = [
            ("GET", "/api/elections/current/"),
            ("GET", "/api/elections/status/"),
            ("GET", "/api/elections/results/"),
            ("POST", "/api/voting/cast/"),
            ("POST", "/api/admin/elections/start/"),
            ("POST", "/api/admin/elections/close/"),
            ("POST", "/api/admin/elections/publish/"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(
                    url,
                    data=json.dumps({"election_id": "x"}),
                    content_type="application/json",
                )
            assert resp.status_code == 401, f"Expected 401 for {method} {url}"

    def test_login_lockout_flow(self):
        """Brute force login attempt gets locked after threshold."""
        student = make_student("LOCK001")
        client = Client(enforce_csrf_checks=False)

        # 5 failed attempts
        for _ in range(5):
            resp = client.post(
                "/api/auth/login/",
                data=json.dumps({"student_id": "LOCK001", "date_of_birth": "1999-01-01"}),
                content_type="application/json",
            )
            assert resp.status_code == 401

        # Account should be locked
        student.refresh_from_db()
        assert student.is_locked is True

        # Even correct credentials should fail
        resp = client.post(
            "/api/auth/login/",
            data=json.dumps({"student_id": "LOCK001", "date_of_birth": "2000-01-01"}),
            content_type="application/json",
        )
        assert resp.status_code == 401
        assert "locked" in resp.json()["error"].lower()
