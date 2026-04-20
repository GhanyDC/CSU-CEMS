"""
Read-only audit command: report valid votes per College Representative seat.

Reconstructs ballot ownership via SHA-256 hashes, compares each voter's
college_snapshot against the allowed college inferred from the position title,
and reports raw / valid / invalid vote counts plus turnout per seat.

NO DATA IS MODIFIED BY THIS COMMAND.
"""

import csv
import json
import io
import re
import sys
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.elections.models import Election, EligibleVoter, Position, Candidate
from apps.voting.models import Ballot, BallotSelection


# ── Normalisation ────────────────────────────────────────────────────────────

_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u002D\uFE58\uFE63\uFF0D]+")


def _normalize_college(name: str) -> str:
    """
    Lowercase, strip, collapse dashes, and remove a leading 'college of '
    prefix so that two college names can be compared safely.
    """
    s = name.strip().lower()
    s = _DASH_RE.sub("-", s)
    if s.startswith("college of "):
        s = s[len("college of "):]
    return s


def _extract_college_from_title(title: str) -> str | None:
    """
    Given a position title like
        'College Representative – Humanities and Social Sciences'
    return the part after the em-dash separator.
    Tries em-dash first, then en-dash, then plain hyphen.
    Returns None if no separator found.
    """
    for sep in (" \u2013 ", " \u2014 ", " - "):
        if sep in title:
            return title.split(sep, 1)[1].strip()
    return None


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
        positions = self._load_college_rep_positions(election)
        hash_to_voter = self._build_hash_to_voter(election)

        report = self._build_report(election, positions, hash_to_voter)

        fmt = options["output_format"]
        if fmt == "table":
            self._render_table(report)
        elif fmt == "csv":
            self._render_csv(report)
        elif fmt == "json":
            self._render_json(report)

    # ── Data loading (read-only) ─────────────────────────────────────────────

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

    def _load_college_rep_positions(self, election: Election) -> list[Position]:
        positions = list(
            Position.objects.filter(
                election=election,
                category=Position.Category.HOUSE_COLLEGE,
            ).order_by("order", "title")
        )
        if not positions:
            raise CommandError(
                "No College Representative (house_college) positions found "
                "for this election."
            )
        return positions

    def _build_hash_to_voter(self, election: Election) -> dict[str, EligibleVoter]:
        """
        For every eligible voter in this election, compute the salted SHA-256
        hash and return a dict  {hash_hex: EligibleVoter}.
        """
        voters = (
            EligibleVoter.objects
            .filter(election=election)
            .select_related("student")
        )
        mapping: dict[str, EligibleVoter] = {}
        election_pk_str = str(election.pk)
        for ev in voters.iterator(chunk_size=2000):
            h = Ballot.hash_student_id(ev.student.student_id, election_pk_str)
            mapping[h] = ev
        return mapping

    # ── Audit logic ──────────────────────────────────────────────────────────

    def _build_report(self, election, positions, hash_to_voter):
        """Return a list of seat-report dicts, one per college-rep position."""
        # Pre-count registered voters per normalised college
        college_voter_counts: dict[str, int] = defaultdict(int)
        college_display: dict[str, str] = {}
        for ev in hash_to_voter.values():
            norm = _normalize_college(ev.college_snapshot)
            college_voter_counts[norm] += 1
            college_display[norm] = ev.college_snapshot  # keep last seen display

        report: list[dict] = []

        for pos in positions:
            raw_college = _extract_college_from_title(pos.title)
            if raw_college is None:
                self.stderr.write(
                    self.style.WARNING(
                        f"Could not parse college from position title: "
                        f"'{pos.title}' — skipping."
                    )
                )
                continue

            norm_allowed = _normalize_college(raw_college)
            display_college = college_display.get(
                norm_allowed, f"College of {raw_college}"
            )
            registered = college_voter_counts.get(norm_allowed, 0)

            # Fetch all BallotSelections for this position
            selections = (
                BallotSelection.objects
                .filter(position=pos)
                .select_related("ballot", "candidate")
            )

            # Per-candidate accumulators
            cand_raw: dict[str, int] = defaultdict(int)
            cand_valid: dict[str, int] = defaultdict(int)
            cand_invalid: dict[str, int] = defaultdict(int)
            cand_names: dict[str, str] = {}

            total_raw = 0
            total_valid = 0
            total_invalid = 0
            unmatched = 0

            for sel in selections.iterator(chunk_size=2000):
                cid = str(sel.candidate_id)
                cand_names[cid] = sel.candidate.full_name
                cand_raw[cid] += 1
                total_raw += 1

                voter = hash_to_voter.get(sel.ballot.hashed_student_id)
                if voter is None:
                    unmatched += 1
                    # Count as raw but not valid
                    cand_invalid[cid] += 1
                    total_invalid += 1
                    continue

                voter_norm = _normalize_college(voter.college_snapshot)
                if voter_norm == norm_allowed:
                    cand_valid[cid] += 1
                    total_valid += 1
                else:
                    cand_invalid[cid] += 1
                    total_invalid += 1

            turnout = (
                (total_valid / registered * 100) if registered > 0 else 0.0
            )

            # Build candidate rows sorted by valid desc
            candidates = []
            for cid, name in sorted(
                cand_names.items(), key=lambda kv: cand_valid.get(kv[0], 0), reverse=True
            ):
                candidates.append({
                    "name": name,
                    "raw_votes": cand_raw[cid],
                    "valid_votes": cand_valid[cid],
                    "invalid_votes": cand_invalid[cid],
                })

            report.append({
                "election_id": str(election.pk),
                "election_name": election.name,
                "position_id": str(pos.pk),
                "position_title": pos.title,
                "allowed_college": display_college,
                "registered_voters": registered,
                "total_raw_votes": total_raw,
                "total_valid_votes": total_valid,
                "total_invalid_votes": total_invalid,
                "unmatched_ballots": unmatched,
                "valid_turnout_pct": round(turnout, 2),
                "candidates": candidates,
            })

        return report

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
