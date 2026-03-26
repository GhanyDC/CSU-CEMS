"""
Management command to import students from a CSV file into the voter registry.

Usage:
    python manage.py import_students path/to/students.csv
    python manage.py import_students path/to/students.csv --dry-run
    python manage.py import_students path/to/students.csv --update

CSV format (header row required):
    student_id, full_name, date_of_birth, college, course, year

Example:
    student_id,full_name,date_of_birth,college,course,year
    2024-00001,Juan Dela Cruz,2002-05-15,College of Engineering,BSEE,3
"""
import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Student


class Command(BaseCommand):
    help = "Import students from a CSV file into the voter registry."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to the CSV file containing student records.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the CSV without writing to the database.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing students with new data (default: skip existing).",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_file"]
        dry_run = options["dry_run"]
        update_existing = options["update"]

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")
        except Exception as e:
            raise CommandError(f"Error reading CSV: {e}")

        required_fields = {"student_id", "full_name", "date_of_birth"}
        if rows:
            header_fields = set(rows[0].keys())
            missing = required_fields - header_fields
            if missing:
                raise CommandError(
                    f"CSV is missing required columns: {', '.join(sorted(missing))}"
                )

        created = 0
        updated = 0
        skipped = 0
        errors = []

        for i, row in enumerate(rows, start=2):  # start=2 (header is row 1)
            student_id = (row.get("student_id") or "").strip()
            full_name = (row.get("full_name") or "").strip()
            dob_raw = (row.get("date_of_birth") or "").strip()
            college = (row.get("college") or "").strip()
            course = (row.get("course") or "").strip()
            year_raw = (row.get("year") or "").strip()

            if not student_id or not full_name or not dob_raw:
                errors.append(f"Row {i}: missing required field(s).")
                continue

            try:
                dob = date.fromisoformat(dob_raw)
            except (ValueError, TypeError):
                errors.append(f"Row {i}: invalid date '{dob_raw}' for {student_id}.")
                continue

            try:
                year = int(year_raw) if year_raw else 1
            except ValueError:
                errors.append(f"Row {i}: invalid year '{year_raw}' for {student_id}.")
                continue

            if dry_run:
                self.stdout.write(f"  [DRY-RUN] Would import: {student_id} - {full_name}")
                created += 1
                continue

            with transaction.atomic():
                existing = Student.objects.filter(student_id=student_id).first()
                if existing:
                    if update_existing:
                        existing.full_name = full_name
                        existing.date_of_birth = dob
                        existing.college = college
                        existing.course = course
                        existing.year = year
                        existing.save(
                            update_fields=["full_name", "date_of_birth", "college", "course", "year"]
                        )
                        updated += 1
                    else:
                        skipped += 1
                else:
                    Student.objects.create(
                        student_id=student_id,
                        full_name=full_name,
                        date_of_birth=dob,
                        college=college,
                        course=course,
                        year=year,
                    )
                    created += 1

        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN — no records written."))
        self.stdout.write(self.style.SUCCESS(f"Created: {created}"))
        if updated:
            self.stdout.write(self.style.SUCCESS(f"Updated: {updated}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped (existing): {skipped}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors: {len(errors)}"))
            for err in errors:
                self.stdout.write(self.style.ERROR(f"  {err}"))
