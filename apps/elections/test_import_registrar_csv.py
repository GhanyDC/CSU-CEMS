from __future__ import annotations

import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.accounts.models import Student
from apps.elections.models import RegistrarImportBatch, RegistrarRecord


HEADERS = "student_id,full_name,date_of_birth,college,course,year\n"
COLLEGE = "College of Information and Computing Sciences"


class ImportRegistrarCsvCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _csv_path(self, body: str, *, headers: str = HEADERS, bom: bool = False) -> Path:
        path = Path(self.temp_dir.name) / "registrar.csv"
        payload = (headers + body).encode("utf-8")
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + payload)
        return path

    def _run(self, path: Path, *, batch_name: str = "Test Masterlist", commit=False):
        stdout = StringIO()
        call_command(
            "import_registrar_csv",
            str(path),
            batch_name=batch_name,
            academic_year="2026-2027",
            commit=commit,
            stdout=stdout,
        )
        return stdout.getvalue()

    def _row(
        self,
        student_id: str = "26-00001",
        date_of_birth: str = "2000-04-09",
        *,
        full_name: str = "Test Student",
        course: str = "BS Computer Science",
        year: str = "1",
    ) -> str:
        return (
            f"{student_id},{full_name},{date_of_birth},{COLLEGE},"
            f"{course},{year}\n"
        )

    def test_iso_date_is_accepted(self):
        self._run(self._csv_path(self._row(date_of_birth="2000-04-09")), commit=True)

        self.assertEqual(Student.objects.get().date_of_birth, date(2000, 4, 9))

    def test_single_digit_month_and_day_are_normalized(self):
        self._run(self._csv_path(self._row(date_of_birth="4/9/1997")), commit=True)

        self.assertEqual(Student.objects.get().date_of_birth, date(1997, 4, 9))

    def test_zero_padded_month_and_day_are_normalized(self):
        self._run(self._csv_path(self._row(date_of_birth="10/30/1995")), commit=True)

        self.assertEqual(Student.objects.get().date_of_birth, date(1995, 10, 30))

    def test_invalid_date_reports_row_student_and_original_value(self):
        path = self._csv_path(self._row("26-00009", "2/30/2000"))

        with self.assertRaises(CommandError) as raised:
            self._run(path, commit=True)

        message = str(raised.exception)
        self.assertIn("Row 1", message)
        self.assertIn("26-00009", message)
        self.assertIn("2/30/2000", message)
        self.assertFalse(Student.objects.exists())

    def test_day_month_year_format_is_not_accepted(self):
        path = self._csv_path(self._row(date_of_birth="30/10/1995"))

        with self.assertRaisesMessage(CommandError, "30/10/1995"):
            self._run(path, commit=True)
        self.assertFalse(Student.objects.exists())

    def test_exact_headers_are_required(self):
        headers = "student_id,full_name,college,date_of_birth,course,year\n"
        path = self._csv_path(self._row(), headers=headers)

        with self.assertRaisesMessage(CommandError, "CSV headers must be exactly"):
            self._run(path)

    def test_duplicate_student_ids_are_rejected(self):
        path = self._csv_path(self._row() + self._row(full_name="Duplicate Student"))

        with self.assertRaisesMessage(CommandError, "duplicate student ID"):
            self._run(path, commit=True)
        self.assertFalse(Student.objects.exists())

    def test_utf8_bom_is_rejected(self):
        path = self._csv_path(self._row(), bom=True)

        with self.assertRaisesMessage(CommandError, "UTF-8 BOM"):
            self._run(path, commit=True)
        self.assertFalse(Student.objects.exists())

    def test_dry_run_leaves_no_database_data(self):
        output = self._run(self._csv_path(self._row(date_of_birth="4/9/1997")))

        self.assertIn("Dry run passed", output)
        self.assertFalse(Student.objects.exists())
        self.assertFalse(RegistrarImportBatch.objects.exists())
        self.assertFalse(RegistrarRecord.objects.exists())

    def test_commit_creates_then_reuses_batch_and_updates_record(self):
        batch_name = "SY 2026-2027 Masterlist"
        self._run(self._csv_path(self._row()), batch_name=batch_name, commit=True)
        self._run(
            self._csv_path(
                self._row(
                    date_of_birth="4/9/1997",
                    full_name="Updated Student",
                    course="BS Information Technology",
                    year="2",
                )
            ),
            batch_name=batch_name,
            commit=True,
        )

        student = Student.objects.get(student_id="26-00001")
        batch = RegistrarImportBatch.objects.get(name=batch_name)
        record = RegistrarRecord.objects.get(batch=batch, student_identifier="26-00001")
        self.assertEqual(RegistrarImportBatch.objects.count(), 1)
        self.assertEqual(RegistrarRecord.objects.count(), 1)
        self.assertEqual(batch.academic_year, "2026-2027")
        self.assertEqual(batch.total_imported, 1)
        self.assertEqual(student.full_name, "Updated Student")
        self.assertEqual(student.date_of_birth, date(1997, 4, 9))
        self.assertEqual(student.year, 2)
        self.assertEqual(record.student, student)
        self.assertEqual(record.full_name, "Updated Student")
        self.assertEqual(record.date_of_birth, date(1997, 4, 9))
        self.assertEqual(record.year_level, 2)

    def test_service_row_error_rolls_back_entire_transaction(self):
        body = self._row("26-00001") + self._row("26-00002", year="0")
        path = self._csv_path(body)

        with self.assertRaisesMessage(CommandError, "Importer reported row errors"):
            self._run(path, commit=True)

        self.assertFalse(Student.objects.exists())
        self.assertFalse(RegistrarImportBatch.objects.exists())
        self.assertFalse(RegistrarRecord.objects.exists())
