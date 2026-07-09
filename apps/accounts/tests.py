import json
from datetime import date

from django.test import Client, TestCase

from apps.accounts.models import Student
from apps.elections.models import RegistrarImportBatch, RegistrarRecord


class StudentLoginRegistrarBatchTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_id="LOGIN-001",
            full_name="Login Student",
            date_of_birth=date(2001, 1, 2),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=1,
        )
        self.client = Client()

    def _login(self):
        return self.client.post(
            "/api/auth/login/",
            data=json.dumps({
                "student_id": self.student.student_id,
                "date_of_birth": "2001-01-02",
            }),
            content_type="application/json",
        )

    def test_student_without_active_registrar_batch_membership_cannot_log_in(self):
        response = self._login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_student_with_active_registrar_batch_membership_can_log_in(self):
        batch = RegistrarImportBatch.objects.create(
            name="AY 2026-2027",
            academic_year="2026-2027",
            status=RegistrarImportBatch.Status.ACTIVE,
        )
        RegistrarRecord.objects.create(
            batch=batch,
            student=self.student,
            student_identifier=self.student.student_id,
            full_name=self.student.full_name,
            date_of_birth=self.student.date_of_birth,
            college=self.student.college,
            course=self.student.course,
            year_level=self.student.year,
            status=RegistrarRecord.Status.ACTIVE,
        )

        response = self._login()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
