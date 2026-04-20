"""
Read-only audit command: report valid votes per College Representative seat.

Delegates computation to ``CollegeRepAuditService`` and renders the result
in table, CSV, or JSON format.

NO DATA IS MODIFIED BY THIS COMMAND.
"""

import csv
import io
import json

from django.core.management.base import BaseCommand, CommandError

from apps.elections.audit_services import CollegeRepAuditService
from apps.elections.models import Election


# ── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Report valid / invalid votes per College Representative seat for a "
        "given election.  Read-only — no data is modified."
    )

    # ── CLI arguments ────────────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "--election-id",
            required=True,
            help="UUID of the election to audit.",
        )
        parser.add_argument(
            "--format",
            choices=("table", "csv", "json"),
            default="table",
            dest="output_format",
            help="Output format (default: table).",
        )

    # ── Entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        election = self._load_election(options["election_id"])

        positions = CollegeRepAuditService.get_college_rep_positions(election)
        if not positions:
            raise CommandError(
                "No College Representative (house_college) positions found "
                "for this election."
            )

        report = CollegeRepAuditService.compute_college_rep_audit(
            election, positions=positions,
        )

        fmt = options["output_format"]
        if fmt == "table":
            self._render_table(report)
        elif fmt == "csv":
            self._render_csv(report)
        elif fmt == "json":
            self._render_json(report)

    # ── Data loading ─────────────────────────────────────────────────────────

    def _load_election(self, election_id: str) -> Election:
        try:
            election = Election.objects.get(pk=election_id)
        except (Election.DoesNotExist, ValueError):
            raise CommandError(f"Election '{election_id}' not found.")

        if election.status not in (Election.Status.CLOSED, Election.Status.PUBLISHED):
            self.stderr.write(
                self.style.WARNING(
                    f"Warning: election status is '{election.status}' "
                    f"(expected closed or published).  Proceeding anyway."
                )
            )
        return election

    # ── Renderers ────────────────────────────────────────────────────────────

    def _render_table(self, report):
        """Human-readable block-per-position output."""
        sep = "=" * 78

        self.stdout.write(f"\n{sep}")
        self.stdout.write("  COLLEGE REPRESENTATIVE VALID-VOTE AUDIT REPORT")
        self.stdout.write(sep)

        if report:
            self.stdout.write(f"  Election : {report[0]['election_name']}")
            self.stdout.write(f"  ID       : {report[0]['election_id']}")
        self.stdout.write(sep)

        for seat in report:
            self.stdout.write(f"\n  Position : {seat['position_title']}")
            self.stdout.write(f"  College  : {seat['allowed_college']}")
            self.stdout.write(f"  Pos. ID  : {seat['position_id']}")
            self.stdout.write("-" * 78)

            # Column headers
            self.stdout.write(
                f"  {'Candidate':<40} {'Raw':>6} {'Valid':>6} {'Invalid':>7}"
            )
            self.stdout.write(f"  {'-'*40} {'-'*6} {'-'*6} {'-'*7}")

            for c in seat["candidates"]:
                self.stdout.write(
                    f"  {c['name']:<40} {c['raw_votes']:>6} "
                    f"{c['valid_votes']:>6} {c['invalid_votes']:>7}"
                )

            self.stdout.write(f"  {'-'*40} {'-'*6} {'-'*6} {'-'*7}")
            self.stdout.write(
                f"  {'TOTALS':<40} {seat['total_raw_votes']:>6} "
                f"{seat['total_valid_votes']:>6} {seat['total_invalid_votes']:>7}"
            )
            self.stdout.write("")
            self.stdout.write(f"  Registered voters in college : {seat['registered_voters']}")
            self.stdout.write(f"  Valid turnout                : {seat['valid_turnout_pct']:.2f}%")
            if seat["unmatched_ballots"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Unmatched ballots (no voter)  : {seat['unmatched_ballots']}"
                    )
                )
            self.stdout.write(sep)

        # Grand totals
        grand_reg = sum(s["registered_voters"] for s in report)
        grand_raw = sum(s["total_raw_votes"] for s in report)
        grand_valid = sum(s["total_valid_votes"] for s in report)
        grand_invalid = sum(s["total_invalid_votes"] for s in report)
        grand_unmatched = sum(s["unmatched_ballots"] for s in report)

        self.stdout.write(f"\n  GRAND TOTALS ACROSS ALL COLLEGE-REP SEATS")
        self.stdout.write(f"  Registered voters : {grand_reg}")
        self.stdout.write(f"  Raw votes         : {grand_raw}")
        self.stdout.write(f"  Valid votes       : {grand_valid}")
        self.stdout.write(f"  Invalid votes     : {grand_invalid}")
        if grand_unmatched:
            self.stdout.write(
                self.style.WARNING(f"  Unmatched ballots : {grand_unmatched}")
            )
        self.stdout.write(f"\n{sep}\n")

    def _render_csv(self, report):
        """Flat CSV: one row per candidate per position."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "election_id",
            "election_name",
            "position_id",
            "position_title",
            "allowed_college",
            "candidate_name",
            "registered_voters",
            "raw_votes",
            "valid_votes",
            "invalid_votes",
            "valid_turnout_pct",
            "unmatched_ballots",
        ])
        for seat in report:
            for c in seat["candidates"]:
                writer.writerow([
                    seat["election_id"],
                    seat["election_name"],
                    seat["position_id"],
                    seat["position_title"],
                    seat["allowed_college"],
                    c["name"],
                    seat["registered_voters"],
                    c["raw_votes"],
                    c["valid_votes"],
                    c["invalid_votes"],
                    seat["valid_turnout_pct"],
                    seat["unmatched_ballots"],
                ])
        self.stdout.write(buf.getvalue())

    def _render_json(self, report):
        """Structured JSON output."""
        self.stdout.write(json.dumps(report, indent=2))
