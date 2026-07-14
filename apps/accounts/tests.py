import json
from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.accounts.utils import get_ratelimit_client_ip
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


class LoginSecurityResponseTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = Student.objects.create(
            student_id="SECURITY-001",
            full_name="Security Student",
            date_of_birth=date(2001, 1, 2),
            college="College of Humanities and Social Sciences",
            course="BA Test",
            year=1,
        )
        batch = RegistrarImportBatch.objects.create(
            name="Security Test Batch",
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
        self.client = Client()

    def tearDown(self):
        cache.clear()

    def _student_login(self, student_id=None, dob="2001-01-02", **headers):
        return self.client.post(
            "/api/auth/login/",
            data=json.dumps(
                {
                    "student_id": student_id or self.student.student_id,
                    "date_of_birth": dob,
                }
            ),
            content_type="application/json",
            **headers,
        )

    def test_student_login_returns_200_for_valid_credentials(self):
        response = self._student_login(HTTP_X_REAL_IP="198.51.100.10")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_student_login_returns_401_for_invalid_credentials(self):
        response = self._student_login(
            student_id="UNKNOWN-STUDENT",
            HTTP_X_REAL_IP="198.51.100.11",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_api_csrf_failure_returns_safe_json_403_and_logs_reason(self):
        csrf_client = Client(enforce_csrf_checks=True)

        with self.assertLogs("cems.security", level="WARNING") as captured:
            response = csrf_client.post(
                "/api/auth/login/",
                data=json.dumps(
                    {
                        "student_id": self.student.student_id,
                        "date_of_birth": "2001-01-02",
                    }
                ),
                content_type="application/json",
                HTTP_X_REAL_IP="198.51.100.12",
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertFalse(response.json()["success"])
        self.assertNotIn("CSRF cookie", response.content.decode())
        self.assertTrue(
            any("CSRF verification failed" in message for message in captured.output)
        )

    @override_settings(CEMS_STUDENT_LOGIN_RATE="1/m")
    def test_student_login_returns_json_429_with_retry_after(self):
        headers = {
            "HTTP_X_REAL_IP": "198.51.100.13",
            "REMOTE_ADDR": "172.18.0.2",
        }
        first = self._student_login(student_id="UNKNOWN-ONE", **headers)
        second = self._student_login(student_id="UNKNOWN-TWO", **headers)

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second["Retry-After"], "60")
        self.assertFalse(second.json()["success"])

    @override_settings(CEMS_STUDENT_LOGIN_RATE="1/m")
    def test_x_real_ip_separates_shared_proxy_buckets(self):
        shared_proxy = "172.18.0.2"
        common = {
            "REMOTE_ADDR": shared_proxy,
            "HTTP_X_FORWARDED_FOR": "203.0.113.250",
        }

        first_a = self._student_login(
            student_id="UNKNOWN-A1",
            HTTP_X_REAL_IP="198.51.100.20",
            **common,
        )
        second_a = self._student_login(
            student_id="UNKNOWN-A2",
            HTTP_X_REAL_IP="198.51.100.20",
            **common,
        )
        first_b = self._student_login(
            student_id="UNKNOWN-B1",
            HTTP_X_REAL_IP="198.51.100.21",
            **common,
        )

        self.assertEqual(first_a.status_code, 401)
        self.assertEqual(second_a.status_code, 429)
        self.assertEqual(first_b.status_code, 401)

    def test_five_failed_attempts_still_lock_student_account(self):
        for _ in range(5):
            response = self._student_login(
                dob="2001-01-03",
                HTTP_X_REAL_IP="198.51.100.30",
            )
            self.assertEqual(response.status_code, 401)

        self.student.refresh_from_db()
        self.assertEqual(self.student.failed_attempts, 5)
        self.assertTrue(self.student.is_locked)

        locked_response = self._student_login(HTTP_X_REAL_IP="198.51.100.30")
        self.assertEqual(locked_response.status_code, 401)


class AdminLoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="security-admin",
            password="correct-horse-battery-staple",
        )
        AdminProfile.objects.create(
            user=self.user,
            role=AdminRole.ELECTORAL_BOARD_HEAD,
            display_name="Security Admin",
        )
        self.client = Client()

    def tearDown(self):
        cache.clear()

    def _admin_login(self, username, password, **headers):
        return self.client.post(
            "/api/admin/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
            **headers,
        )

    def test_admin_login_returns_200_and_invalid_credentials_return_401(self):
        invalid = self._admin_login(
            "security-admin",
            "wrong-password",
            HTTP_X_REAL_IP="198.51.100.40",
        )
        valid = self._admin_login(
            "security-admin",
            "correct-horse-battery-staple",
            HTTP_X_REAL_IP="198.51.100.41",
        )

        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(valid.status_code, 200)

    @override_settings(CEMS_ADMIN_LOGIN_RATE="1/m")
    def test_admin_login_returns_json_429_with_retry_after(self):
        headers = {
            "HTTP_X_REAL_IP": "198.51.100.42",
            "REMOTE_ADDR": "172.18.0.2",
        }
        first = self._admin_login("unknown-one", "wrong", **headers)
        second = self._admin_login("unknown-two", "wrong", **headers)

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second["Retry-After"], "60")


class RateLimitClientIPTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_x_real_ip_and_ignores_x_forwarded_for(self):
        request = self.factory.get(
            "/",
            HTTP_X_REAL_IP="198.51.100.50",
            HTTP_X_FORWARDED_FOR="203.0.113.99, 198.51.100.50",
            REMOTE_ADDR="172.18.0.2",
        )

        self.assertEqual(
            get_ratelimit_client_ip("test", request),
            "198.51.100.50",
        )

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get("/", REMOTE_ADDR="192.0.2.10")

        self.assertEqual(
            get_ratelimit_client_ip("test", request),
            "192.0.2.10",
        )
