from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.elections.hybrid_services import HybridElectionError, HybridElectionService
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    HybridImportBatch,
    Position,
)
from apps.elections.services import ElectionLifecycleService, ElectionNotReadyError, ResultService
from apps.voting.models import Ballot, BallotSelection


class HybridElectionTestBase(TestCase):
    def setUp(self):
        now = timezone.now()
        self.election = Election.objects.create(
            name="AY 2026 Hybrid Election",
            election_type=Election.ElectionType.CAMPUS,
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1),
            status=Election.Status.CLOSED,
            voting_mode=Election.VotingMode.HYBRID,
        )
        self.position = Position.objects.create(
            election=self.election,
            title="President",
            category=Position.Category.EXECUTIVE,
            max_selections=1,
            order=1,
        )
        self.candidate_a = Candidate.objects.create(
            position=self.position,
            full_name="Alice Cruz",
            party="Unity",
            is_active=True,
        )
        self.candidate_b = Candidate.objects.create(
            position=self.position,
            full_name="Ben Dela",
            party="Forward",
            is_active=True,
        )
        self.students = []
        for index in range(1, 5):
            student = Student.objects.create(
                student_id=f"2026-00{index}",
                full_name=f"Student {index}",
                date_of_birth=date(2000, 1, index),
                college="College of Engineering",
                course="BS Test",
                year=1,
            )
            self.students.append(student)
            EligibleVoter.objects.create(
                election=self.election,
                student=student,
                college_snapshot=student.college,
            )

    def cast_online_vote(self, student: Student, candidate: Candidate) -> Ballot:
        ballot = Ballot.objects.create(
            election=self.election,
            hashed_student_id=Ballot.hash_student_id(student.student_id, str(self.election.pk)),
        )
        BallotSelection.objects.create(
            ballot=ballot,
            position=self.position,
            candidate=candidate,
        )
        return ballot

    def import_valid_roster(self):
        return HybridElectionService.import_onsite_roster(
            self.election,
            [{"student_id": self.students[1].student_id}, {"student_id": self.students[2].student_id}],
            imported_by="Tester",
            source_filename="onsite_roster.csv",
        )

    def import_valid_tally(self):
        return HybridElectionService.import_onsite_tally(
            self.election,
            [
                {
                    "position_id": str(self.position.pk),
                    "position_title": self.position.title,
                    "candidate_id": str(self.candidate_a.pk),
                    "candidate_name": self.candidate_a.full_name,
                    "onsite_votes": "1",
                },
                {
                    "position_id": str(self.position.pk),
                    "position_title": self.position.title,
                    "candidate_id": str(self.candidate_b.pk),
                    "candidate_name": self.candidate_b.full_name,
                    "onsite_votes": "1",
                },
            ],
            imported_by="Tester",
            source_filename="onsite_tally.csv",
        )


class HybridElectionServiceTests(HybridElectionTestBase):
    def test_election_defaults_to_online_voting_mode(self):
        election = Election.objects.create(
            name="Default Online Election",
            election_type=Election.ElectionType.CAMPUS,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(election.voting_mode, Election.VotingMode.ONLINE)

    def test_roster_import_rejects_online_overlap_and_reimport_supersedes_previous_batch(self):
        self.cast_online_vote(self.students[0], self.candidate_a)

        with self.assertRaises(HybridElectionError) as ctx:
            HybridElectionService.import_onsite_roster(
                self.election,
                [{"student_id": self.students[0].student_id}],
                imported_by="Tester",
                source_filename="invalid_roster.csv",
            )
        self.assertIn("already voted online", " ".join(ctx.exception.summary.get("errors", [])))

        first = HybridElectionService.import_onsite_roster(
            self.election,
            [{"student_id": self.students[1].student_id}],
            imported_by="Tester",
            source_filename="roster_one.csv",
        )
        self.assertEqual(first["batch"]["status"], HybridImportBatch.Status.ACTIVE)
        self.assertEqual(
            HybridImportBatch.objects.filter(
                election=self.election,
                batch_type=HybridImportBatch.BatchType.ROSTER,
                status=HybridImportBatch.Status.ACTIVE,
            ).count(),
            1,
        )

        HybridElectionService.import_onsite_roster(
            self.election,
            [{"student_id": self.students[2].student_id}],
            imported_by="Tester",
            source_filename="roster_two.csv",
        )
        self.assertEqual(
            HybridImportBatch.objects.filter(
                election=self.election,
                batch_type=HybridImportBatch.BatchType.ROSTER,
                status=HybridImportBatch.Status.ACTIVE,
            ).count(),
            1,
        )
        self.assertEqual(
            HybridImportBatch.objects.filter(
                election=self.election,
                batch_type=HybridImportBatch.BatchType.ROSTER,
                status=HybridImportBatch.Status.SUPERSEDED,
            ).count(),
            1,
        )

    def test_tally_import_requires_full_candidate_coverage(self):
        self.import_valid_roster()
        with self.assertRaises(HybridElectionError) as ctx:
            HybridElectionService.import_onsite_tally(
                self.election,
                [
                    {
                        "position_id": str(self.position.pk),
                        "position_title": self.position.title,
                        "candidate_id": str(self.candidate_a.pk),
                        "candidate_name": self.candidate_a.full_name,
                        "onsite_votes": "2",
                    }
                ],
                imported_by="Tester",
                source_filename="incomplete_tally.csv",
            )
        self.assertIn("missing required candidate rows", " ".join(ctx.exception.summary.get("errors", [])))

    def test_combined_results_and_publish_gate_for_hybrid(self):
        self.cast_online_vote(self.students[0], self.candidate_a)

        with self.assertRaises(ElectionNotReadyError):
            ElectionLifecycleService.publish_results(self.election, performed_by="tester")

        self.import_valid_roster()
        self.import_valid_tally()

        results = ResultService.compute_results_with_thresholds(self.election)
        self.assertEqual(results["counting_mode"], "combined_official")
        self.assertEqual(results["total_ballots"], 3)
        position = results["positions"][0]
        self.assertEqual(position["counting_mode"], "combined_official")
        self.assertEqual(position["total_votes"], 3)
        self.assertEqual(position["winner"], "Alice Cruz")
        alice = next(row for row in position["results"] if row["candidate"] == "Alice Cruz")
        ben = next(row for row in position["results"] if row["candidate"] == "Ben Dela")
        self.assertEqual(alice["online_votes"], 1)
        self.assertEqual(alice["onsite_votes"], 1)
        self.assertEqual(alice["combined_votes"], 2)
        self.assertEqual(ben["combined_votes"], 1)

        published = ElectionLifecycleService.publish_results(self.election, performed_by="tester")
        self.assertEqual(published.status, Election.Status.PUBLISHED)


class HybridElectionApiTests(HybridElectionTestBase):
    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="ebhead",
            password="password123",
        )
        AdminProfile.objects.create(
            user=self.admin_user,
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="EB Head",
            is_active=True,
        )
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)

    def test_admin_hybrid_roster_import_endpoint_returns_hybrid_summary(self):
        csv_file = SimpleUploadedFile(
            "onsite_roster.csv",
            f"student_id\n{self.students[1].student_id}\n{self.students[2].student_id}\n".encode("utf-8"),
            content_type="text/csv",
        )
        response = self.admin_client.post(
            f"/api/admin/elections/setup/{self.election.pk}/hybrid/roster/import/",
            {"csv_file": csv_file},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["hybrid"]["turnout"]["onsite_voted"], 2)
        self.assertEqual(payload["hybrid"]["roster_import"]["active"]["status"], "active")

    def test_student_results_hide_hybrid_source_split_fields(self):
        self.cast_online_vote(self.students[0], self.candidate_a)
        self.import_valid_roster()
        self.import_valid_tally()
        self.election.status = Election.Status.PUBLISHED
        self.election.save(update_fields=["status", "updated_at"])

        student_client = Client()
        session = student_client.session
        session["authenticated_student_id"] = str(self.students[0].pk)
        session.save()

        response = student_client.get(f"/api/elections/results/{self.election.pk}/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertNotIn("online_ballots", payload)
        self.assertNotIn("onsite_ballots", payload)
        candidate_row = payload["positions"][0]["results"][0]
        self.assertIn("votes", candidate_row)
        self.assertNotIn("online_votes", candidate_row)
        self.assertNotIn("onsite_votes", candidate_row)
