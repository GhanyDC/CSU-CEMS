from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.elections.models import RegistrarImportBatch
from apps.elections.services import RegistrarBatchService, VoterRollError

REQUIRED_HEADERS = (
    "student_id",
    "full_name",
    "date_of_birth",
    "college",
    "course",
    "year",
)


class Command(BaseCommand):
    help = "Validate and import a CEMS registrar CSV. Defaults to rollback dry-run."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--batch-id")
        target.add_argument("--batch-name")
        parser.add_argument("--academic-year", default="")
        parser.add_argument("--description", default="")
        parser.add_argument("--imported-by", default="local-management-command")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Persist changes. Without this flag the entire import is rolled back.",
        )

    def handle(self, *args, **options):
        csv_path: Path = options["csv_path"]
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        raw = csv_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CommandError("CSV has a UTF-8 BOM. Regenerate it as UTF-8 without BOM.")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CommandError("CSV is not valid UTF-8.") from exc

        reader = csv.DictReader(text.splitlines())
        headers = tuple(reader.fieldnames or ())
        if headers != REQUIRED_HEADERS:
            raise CommandError(
                f"CSV headers must be exactly {REQUIRED_HEADERS}; got {headers}."
            )
        rows = list(reader)
        if not rows:
            raise CommandError("CSV contains no data rows.")

        duplicate_ids = self._duplicate_student_ids(rows)
        if duplicate_ids:
            preview = ", ".join(duplicate_ids[:10])
            raise CommandError(
                f"CSV contains {len(duplicate_ids)} duplicate student ID(s): {preview}"
            )

        rows = self._normalize_birthdates(rows)

        commit = options["commit"]
        mode = "COMMIT" if commit else "DRY RUN / ROLLBACK"
        self.stdout.write(self.style.WARNING(f"Mode: {mode}"))
        self.stdout.write(f"Rows: {len(rows):,}")

        try:
            with transaction.atomic():
                batch = self._resolve_batch(options)
                summary = RegistrarBatchService.import_students_to_batch(batch, rows)
                self._print_summary(batch, summary)

                errors = summary.get("errors") or []
                if errors:
                    raise CommandError(
                        "Importer reported row errors; transaction will be rolled back.\n- "
                        + "\n- ".join(errors)
                    )

                if not commit:
                    transaction.set_rollback(True)
        except VoterRollError as exc:
            raise CommandError(str(exc)) from exc

        if commit:
            self.stdout.write(self.style.SUCCESS("Registrar import committed successfully."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run passed. No database changes were saved. Re-run with --commit to persist."
                )
            )

    @staticmethod
    def _duplicate_student_ids(rows):
        seen = set()
        duplicates = set()
        for row in rows:
            sid = (row.get("student_id") or "").strip()
            if sid in seen:
                duplicates.add(sid)
            seen.add(sid)
        return sorted(duplicates)

    @staticmethod
    def _normalize_birthdates(rows):
        normalized_rows = []
        for row_number, row in enumerate(rows, start=1):
            normalized_row = row.copy()
            original_value = row.get("date_of_birth")
            raw_value = (original_value or "").strip()

            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_value):
                    parsed = date.fromisoformat(raw_value)
                elif re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw_value):
                    parsed = datetime.strptime(raw_value, "%m/%d/%Y").date()
                else:
                    raise ValueError("unsupported date format")
            except (ValueError, TypeError) as exc:
                student_id = (row.get("student_id") or "").strip()
                raise CommandError(
                    f"Row {row_number}: invalid date_of_birth for {student_id}: "
                    f"{original_value!r}"
                ) from exc

            normalized_row["date_of_birth"] = parsed.isoformat()
            normalized_rows.append(normalized_row)

        return normalized_rows

    def _resolve_batch(self, options):
        batch_id = options.get("batch_id")
        if batch_id:
            try:
                batch = RegistrarImportBatch.objects.get(pk=batch_id)
            except RegistrarImportBatch.DoesNotExist as exc:
                raise CommandError(f"Registrar batch not found: {batch_id}") from exc
            if batch.status != RegistrarImportBatch.Status.ACTIVE:
                raise CommandError(f"Registrar batch is archived: {batch.name} ({batch.pk})")
            return batch

        batch_name = (options.get("batch_name") or "").strip()
        existing = RegistrarImportBatch.objects.filter(name=batch_name).first()
        if existing:
            if existing.status != RegistrarImportBatch.Status.ACTIVE:
                raise CommandError(f"Registrar batch is archived: {existing.name} ({existing.pk})")
            self.stdout.write(f"Using existing batch: {existing.name} ({existing.pk})")
            return existing

        batch = RegistrarBatchService.create_batch(
            name=batch_name,
            academic_year=options.get("academic_year", ""),
            description=options.get("description", ""),
            imported_by=options.get("imported_by", ""),
        )
        self.stdout.write(f"Created temporary/new batch: {batch.name} ({batch.pk})")
        return batch

    def _print_summary(self, batch, summary):
        self.stdout.write(f"Batch: {batch.name} ({batch.pk})")
        self.stdout.write(f"Students created: {summary['created']:,}")
        self.stdout.write(f"Students updated: {summary['updated']:,}")
        self.stdout.write(f"Batch records created: {summary['records_created']:,}")
        self.stdout.write(f"Batch records updated: {summary['records_updated']:,}")
        self.stdout.write(f"Skipped: {summary['skipped']:,}")
        self.stdout.write(f"Total records in batch: {summary['total_records']:,}")
