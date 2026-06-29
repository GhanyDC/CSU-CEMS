from __future__ import annotations

import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.elections.hybrid_services import HybridElectionError, HybridElectionService
from apps.elections.models import (
    Candidate,
    EnrollmentRecord,
    Election,
    EligibleVoter,
    HybridImportBatch,
    Position,
    SchoolYear,
    VoterRegistration,
)
from apps.elections.services import (
    ElectionLifecycleService,
    ElectionNotReadyError,
    ResultService,
    VoterRollService,
)
from apps.elections.setup_services import ReadinessService
from apps.voting.models import Ballot, BallotSelection
from apps.voting.services import BallotService, InvalidSelectionError, VoterNotEligibleError


class CollegeRepresentativeScopeTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.election = Election.objects.create(
            name="AY 2026 Campus Election",
            election_type=Election.ElectionType.CAMPUS,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            status=Election.Status.ACTIVE,
        )
        self.president = Position.objects.create(
            election=self.election,
            title="President",
            category=Position.Category.EXECUTIVE,
            max_selections=1,
            order=1,
        )
        self.hss_rep = Position.objects.create(
            election=self.election,
            title="College Representative - Humanities and Social Sciences",
            category=Position.Category.HOUSE_COLLEGE,
            scope_college="College of Humanities and Social Sciences",
            max_selections=1,
            order=2,
        )
        self.cics_rep = Position.objects.create(
            election=self.election,
            title="College Representative - Information and Computing Sciences",
            category=Position.Category.HOUSE_COLLEGE,
            scope_college="College of Information and Computing Sciences",
            max_selections=1,
            order=3,
        )
        self.president_candidate = Candidate.objects.create(
            position=self.president,
            full_name="Pat President",
            is_active=True,
        )
        self.hss_candidate = Candidate.objects.create(
            position=self.hss_rep,
            full_name="Hanna HSS",
            college="College of Humanities and Social Sciences",
            is_active=True,
        )
        self.cics_candidate = Candidate.objects.create(
            position=self.cics_rep,
            full_name="Cora CICS",
            college="College of Information and Computing Sciences",
            is_active=True,
        )
        self.hss_student = Student.objects.create(
            student_id="HSS-001",
            full_name="HSS Student",
            date_of_birth=date(2000, 1, 1),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=1,
        )
        self.cics_student = Student.objects.create(
            student_id="CICS-001",
            full_name="CICS Student",
            date_of_birth=date(2000, 1, 2),
            college="College of Information and Computing Sciences",
            course="BS Test",
            year=1,
        )
        for student in (self.hss_student, self.cics_student):
            EligibleVoter.objects.create(
                election=self.election,
                student=student,
                college_snapshot=student.college,
            )

    def _student_client(self, student):
        client = Client()
        session = client.session
        session["authenticated_student_id"] = str(student.pk)
        session.save()
        return client

    def test_ballot_only_shows_voters_own_college_rep_seat(self):
        response = self._student_client(self.cics_student).get(
            f"/api/elections/{self.election.pk}/ballot/"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])

        house_positions = [
            position
            for position in payload["positions"]
            if position["category"] == Position.Category.HOUSE_COLLEGE
        ]
        self.assertEqual(len(house_positions), 1)
        self.assertEqual(house_positions[0]["id"], str(self.cics_rep.pk))
        self.assertEqual(
            [candidate["full_name"] for candidate in house_positions[0]["candidates"]],
            ["Cora CICS"],
        )

        visible_candidate_names = {
            candidate["full_name"]
            for position in payload["positions"]
            for candidate in position["candidates"]
        }
        self.assertNotIn("Hanna HSS", visible_candidate_names)

    def test_service_rejects_cross_college_rep_candidate(self):
        with self.assertRaises(InvalidSelectionError):
            BallotService.cast_ballot(
                self.hss_student,
                self.election,
                [(str(self.cics_rep.pk), str(self.cics_candidate.pk))],
            )

        self.assertFalse(Ballot.objects.filter(election=self.election).exists())

    def test_service_accepts_own_college_rep_candidate(self):
        ballot = BallotService.cast_ballot(
            self.cics_student,
            self.election,
            [(str(self.cics_rep.pk), str(self.cics_candidate.pk))],
        )

        self.assertEqual(ballot.election, self.election)
        self.assertTrue(
            BallotSelection.objects.filter(
                ballot=ballot,
                position=self.cics_rep,
                candidate=self.cics_candidate,
            ).exists()
        )

    def test_college_election_rejects_wrong_college_even_if_roll_is_wrong(self):
        now = timezone.now()
        election = Election.objects.create(
            name="HSS College Election",
            election_type=Election.ElectionType.COLLEGE,
            college="College of Humanities and Social Sciences",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            status=Election.Status.ACTIVE,
        )
        position = Position.objects.create(
            election=election,
            title="Governor",
            category=Position.Category.COLLEGE_EXECUTIVE,
            max_selections=1,
            order=1,
        )
        candidate = Candidate.objects.create(
            position=position,
            full_name="Gov Candidate",
            is_active=True,
        )
        EligibleVoter.objects.create(
            election=election,
            student=self.cics_student,
            college_snapshot=self.cics_student.college,
        )

        with self.assertRaises(VoterNotEligibleError):
            BallotService.cast_ballot(
                self.cics_student,
                election,
                [(str(position.pk), str(candidate.pk))],
            )

    def test_readiness_flags_mis_scoped_college_rep_candidate(self):
        self.cics_candidate.college = "College of Nursing"
        self.cics_candidate.save(update_fields=["college"])
        self.election.status = Election.Status.DRAFT
        self.election.save(update_fields=["status", "updated_at"])

        report = ReadinessService.check_readiness(self.election)

        scope_check = next(
            check
            for check in report["checks"]
            if check["name"] == "College representative scopes valid"
        )
        self.assertFalse(scope_check["passed"])
        self.assertIn("mis-scoped", " ".join(report["blocking_issues"]))


class ElectionLifecycleReadinessRegressionTests(TestCase):
    def test_start_election_blocks_unready_draft_without_name_error(self):
        now = timezone.now()
        election = Election.objects.create(
            name="Unready Draft Election",
            election_type=Election.ElectionType.CAMPUS,
            start_time=now,
            end_time=now + timedelta(hours=2),
            status=Election.Status.DRAFT,
        )

        with self.assertRaises(ElectionNotReadyError) as ctx:
            ElectionLifecycleService.start_election(election, performed_by="tester")

        self.assertIn("Cannot start election", str(ctx.exception))


class WebVoterRegistrationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.school_year = SchoolYear.objects.create(
            name="AY 2026-2027",
            academic_year="2026-2027",
            status=SchoolYear.Status.ACTIVE,
        )
        self.hss_student = Student.objects.create(
            student_id="HSS-REG-001",
            full_name="HSS Registrant",
            date_of_birth=date(2001, 2, 1),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=2,
        )
        self.cics_student = Student.objects.create(
            student_id="CICS-REG-001",
            full_name="CICS Registrant",
            date_of_birth=date(2001, 2, 2),
            college="College of Information and Computing Sciences",
            course="BS Test",
            year=2,
        )
        self.inactive_student = Student.objects.create(
            student_id="OLD-REG-001",
            full_name="Inactive Registrant",
            date_of_birth=date(2001, 2, 3),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=2,
        )
        for student in (self.hss_student, self.cics_student):
            EnrollmentRecord.objects.create(
                school_year=self.school_year,
                student=student,
                student_identifier=student.student_id,
                full_name=student.full_name,
                date_of_birth=student.date_of_birth,
                college=student.college,
                course=student.course,
                year_level=student.year,
                status=EnrollmentRecord.Status.ACTIVE,
            )
        self.inactive_enrollment = EnrollmentRecord.objects.create(
            school_year=self.school_year,
            student=self.inactive_student,
            student_identifier=self.inactive_student.student_id,
            full_name=self.inactive_student.full_name,
            date_of_birth=self.inactive_student.date_of_birth,
            college=self.inactive_student.college,
            course=self.inactive_student.course,
            year_level=self.inactive_student.year,
            status=EnrollmentRecord.Status.INACTIVE,
        )
        self.campus_election = Election.objects.create(
            name="Campus Registration Election",
            election_type=Election.ElectionType.CAMPUS,
            school_year=self.school_year,
            registration_enabled=True,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2),
            status=Election.Status.DRAFT,
        )
        self.hss_college_election = Election.objects.create(
            name="HSS Registration Election",
            election_type=Election.ElectionType.COLLEGE,
            college="College of Humanities and Social Sciences",
            school_year=self.school_year,
            registration_enabled=True,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2),
            status=Election.Status.DRAFT,
        )

    def _student_client(self, student):
        client = Client()
        session = client.session
        session["authenticated_student_id"] = str(student.pk)
        session.save()
        return client

    def _add_ready_position(self, election):
        position = Position.objects.create(
            election=election,
            title="President" if election.is_campus else "Governor",
            category=(
                Position.Category.EXECUTIVE
                if election.is_campus
                else Position.Category.COLLEGE_EXECUTIVE
            ),
            max_selections=1,
            order=1,
        )
        Candidate.objects.create(
            position=position,
            full_name="Ready Candidate",
            is_active=True,
        )

    def test_enrolled_student_registers_for_campus_election(self):
        response = self._student_client(self.hss_student).post(
            f"/api/registration/elections/{self.campus_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(
            VoterRegistration.objects.filter(
                election=self.campus_election,
                student=self.hss_student,
                status=VoterRegistration.Status.APPROVED,
            ).exists()
        )
        self.assertTrue(
            EligibleVoter.objects.filter(
                election=self.campus_election,
                student=self.hss_student,
                college_snapshot=self.hss_student.college,
            ).exists()
        )

    def test_enrolled_student_registers_for_own_college_election(self):
        response = self._student_client(self.hss_student).post(
            f"/api/registration/elections/{self.hss_college_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(
            payload["registration"]["college_snapshot"],
            self.hss_student.college,
        )
        self.assertTrue(
            EligibleVoter.objects.filter(
                election=self.hss_college_election,
                student=self.hss_student,
                college_snapshot=self.hss_student.college,
            ).exists()
        )

    def test_available_registrations_are_scoped_to_student_college(self):
        hss_payload = self._student_client(self.hss_student).get(
            "/api/registration/available/"
        ).json()
        cics_payload = self._student_client(self.cics_student).get(
            "/api/registration/available/"
        ).json()

        hss_ids = {e["id"] for e in hss_payload["elections"]}
        cics_ids = {e["id"] for e in cics_payload["elections"]}
        self.assertIn(str(self.campus_election.pk), hss_ids)
        self.assertIn(str(self.hss_college_election.pk), hss_ids)
        self.assertIn(str(self.campus_election.pk), cics_ids)
        self.assertNotIn(str(self.hss_college_election.pk), cics_ids)

    def test_cross_college_registration_is_blocked(self):
        response = self._student_client(self.cics_student).post(
            f"/api/registration/elections/{self.hss_college_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            EligibleVoter.objects.filter(
                election=self.hss_college_election,
                student=self.cics_student,
            ).exists()
        )

    def test_registration_blocked_for_inactive_missing_finalized_disabled_and_non_draft(self):
        missing_student = Student.objects.create(
            student_id="MISS-REG-001",
            full_name="Missing Enrollment",
            date_of_birth=date(2001, 2, 4),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=1,
        )
        disabled = Election.objects.create(
            name="Disabled Registration",
            election_type=Election.ElectionType.CAMPUS,
            school_year=self.school_year,
            registration_enabled=False,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=2),
            status=Election.Status.DRAFT,
        )
        finalized = Election.objects.create(
            name="Finalized Registration",
            election_type=Election.ElectionType.CAMPUS,
            school_year=self.school_year,
            registration_enabled=True,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=2),
            status=Election.Status.DRAFT,
            voter_roll_finalized_at=timezone.now(),
            voter_roll_finalized_by="Tester",
        )
        active = Election.objects.create(
            name="Active Registration",
            election_type=Election.ElectionType.CAMPUS,
            school_year=self.school_year,
            registration_enabled=True,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            status=Election.Status.ACTIVE,
        )

        cases = [
            (self.inactive_student, self.campus_election),
            (missing_student, self.campus_election),
            (self.hss_student, disabled),
            (self.hss_student, finalized),
            (self.hss_student, active),
        ]
        for student, election in cases:
            response = self._student_client(student).post(
                f"/api/registration/elections/{election.pk}/register/",
                data="{}",
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)

    def test_duplicate_registration_is_idempotent(self):
        client = self._student_client(self.hss_student)
        first = client.post(
            f"/api/registration/elections/{self.campus_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )
        second = client.post(
            f"/api/registration/elections/{self.campus_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            EligibleVoter.objects.filter(
                election=self.campus_election,
                student=self.hss_student,
            ).count(),
            1,
        )
        self.assertEqual(
            VoterRegistration.objects.filter(
                election=self.campus_election,
                student=self.hss_student,
            ).count(),
            1,
        )

    def test_readiness_accepts_finalized_web_registrations_and_flags_invalid_enrollment(self):
        self._add_ready_position(self.campus_election)
        self._student_client(self.hss_student).post(
            f"/api/registration/elections/{self.campus_election.pk}/register/",
            data="{}",
            content_type="application/json",
        )
        VoterRollService.finalize_voter_roll(self.campus_election, finalized_by="Tester")
        self.campus_election.refresh_from_db()

        ready_report = ReadinessService.check_readiness(self.campus_election)
        self.assertTrue(ready_report["ready"])

        EnrollmentRecord.objects.filter(
            school_year=self.school_year,
            student=self.hss_student,
        ).update(status=EnrollmentRecord.Status.INACTIVE)

        invalid_report = ReadinessService.check_readiness(self.campus_election)
        self.assertFalse(invalid_report["ready"])
        self.assertIn(
            "Voter roll contains voters outside the linked school-year enrollment.",
            invalid_report["blocking_issues"],
        )


class WebVoterRegistrationAdminApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="operator",
            password="password123",
        )
        AdminProfile.objects.create(
            user=self.admin_user,
            role=AdminRole.ELECTORAL_BOARD_OPERATOR,
            display_name="Operator",
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        now = timezone.now()
        self.election = Election.objects.create(
            name="Admin Registration Election",
            election_type=Election.ElectionType.CAMPUS,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2),
            status=Election.Status.DRAFT,
        )

    def test_admin_can_create_roster_and_enable_registration(self):
        school_year_response = self.client.post(
            "/api/admin/elections/setup/school-years/create/",
            data=json.dumps({
                "name": "AY 2027-2028",
                "academic_year": "2027-2028",
                "activate": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(school_year_response.status_code, 201)
        school_year_id = school_year_response.json()["school_year"]["id"]

        enrollment_response = self.client.post(
            f"/api/admin/elections/setup/school-years/{school_year_id}/enrollments/create/",
            data=json.dumps({
                "student_id": "WEB-ADMIN-001",
                "full_name": "Web Admin Student",
                "date_of_birth": "2002-03-04",
                "college": "College of Humanities and Social Sciences",
                "course": "BA Test",
                "year_level": 1,
            }),
            content_type="application/json",
        )
        self.assertEqual(enrollment_response.status_code, 201)
        self.assertTrue(Student.objects.filter(student_id="WEB-ADMIN-001").exists())

        settings_response = self.client.post(
            f"/api/admin/elections/setup/{self.election.pk}/registration/settings/",
            data=json.dumps({
                "school_year_id": school_year_id,
                "registration_enabled": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(settings_response.status_code, 200)
        self.election.refresh_from_db()
        self.assertEqual(str(self.election.school_year_id), school_year_id)
        self.assertTrue(self.election.registration_enabled)


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

    def test_roster_reimport_supersedes_active_tally_and_blocks_publish(self):
        self.import_valid_roster()
        self.import_valid_tally()
        self.assertTrue(HybridElectionService.has_required_imports(self.election))

        result = HybridElectionService.import_onsite_roster(
            self.election,
            [{"student_id": self.students[3].student_id}],
            imported_by="Tester",
            source_filename="roster_refresh.csv",
        )

        self.assertIn("Existing onsite tally import was cleared", result["message"])
        self.assertFalse(HybridElectionService.has_required_imports(self.election))
        self.assertEqual(
            HybridImportBatch.objects.filter(
                election=self.election,
                batch_type=HybridImportBatch.BatchType.TALLY,
                status=HybridImportBatch.Status.ACTIVE,
            ).count(),
            0,
        )
        self.assertEqual(
            HybridImportBatch.objects.filter(
                election=self.election,
                batch_type=HybridImportBatch.BatchType.TALLY,
                status=HybridImportBatch.Status.SUPERSEDED,
            ).count(),
            1,
        )

        with self.assertRaises(ElectionNotReadyError):
            ElectionLifecycleService.publish_results(self.election, performed_by="tester")

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

    def test_tally_import_rejects_position_totals_above_onsite_turnout_capacity(self):
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
                source_filename="over_limit_tally.csv",
            )

        self.assertIn(
            "exceeds the maximum",
            " ".join(ctx.exception.summary.get("errors", [])),
        )

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
