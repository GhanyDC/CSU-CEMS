"""
Management command to import verification form CSV for an election.

Usage:
    python manage.py import_verification <election_id> verification.csv
    python manage.py import_verification <election_id> verification.csv --dry-run
"""
import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.elections.models import Election
from apps.elections.services import VoterRollError, VoterRollService


class Command(BaseCommand):
    help = "Import a verification form CSV for a specific election."

    def add_arguments(self, parser):
        parser.add_argument("election_id", type=str, help="UUID of the election.")
        parser.add_argument("csv_file", type=str, help="Path to the verification CSV.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the database.",
        )

    def handle(self, *args, **options):
        election_id = options["election_id"]
        csv_path = options["csv_file"]
        dry_run = options["dry_run"]

        try:
            election = Election.objects.get(pk=election_id)
        except (Election.DoesNotExist, ValueError, ValidationError):
            raise CommandError(f"Election not found: {election_id}")

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")
        except Exception as e:
            raise CommandError(f"Error reading CSV: {e}")

        if not rows:
            raise CommandError("CSV file contains no data rows.")

        self.stdout.write(
            f"Parsed {len(rows)} rows for election: {election.name}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes written."))
            return

        try:
            summary = VoterRollService.import_verification(election, rows)
        except VoterRollError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"Import complete: "
            f"created={summary['created']}, "
            f"matched={summary['matched']}, "
            f"unmatched={summary['unmatched']}, "
            f"skipped_duplicate={summary['skipped_duplicate']}"
        ))
