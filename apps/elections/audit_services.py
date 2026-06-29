"""
Reusable read-only audit service for College Representative seats.

Reconstructs ballot ownership via SHA-256 hashes, compares each voter's
college_snapshot against the allowed college inferred from the position title,
and returns raw / valid / invalid vote counts plus turnout per seat.

NO DATA IS MODIFIED BY ANY FUNCTION IN THIS MODULE.
"""

import re
from collections import defaultdict

from apps.elections.models import Election, EligibleVoter, Position
from apps.elections.scope import resolve_position_scope_college
from apps.voting.models import Ballot, BallotSelection


# ── Normalisation helpers ────────────────────────────────────────────────────

_DASH_RE = re.compile(
    r"[\u2010\u2011\u2012\u2013\u2014\u2015\u002D\uFE58\uFE63\uFF0D]+"
)


def normalize_college(name: str) -> str:
    """
    Lowercase, strip, collapse dashes, and remove a leading ``college of ``
    prefix so that two college names can be compared safely.
    """
    s = name.strip().lower()
    s = _DASH_RE.sub("-", s)
    if s.startswith("college of "):
        s = s[len("college of "):]
    return s


def extract_college_from_title(title: str) -> str | None:
    """
    Given a position title like
        ``College Representative – Humanities and Social Sciences``
    return the part after the em-dash separator.

    Tries em-dash first, then en-dash, then plain hyphen.
    Returns *None* if no separator is found.
    """
    for sep in (" \u2013 ", " \u2014 ", " - "):
        if sep in title:
            return title.split(sep, 1)[1].strip()
    return None


# ── Service ──────────────────────────────────────────────────────────────────

class CollegeRepAuditService:
    """Read-only audit computations for College Representative seats."""

    @staticmethod
    def build_hash_to_voter(election: Election) -> dict[str, EligibleVoter]:
        """
        For every eligible voter in *election*, compute the salted SHA-256
        hash and return ``{hash_hex: EligibleVoter}``.
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

    @staticmethod
    def get_college_rep_positions(election: Election) -> list[Position]:
        """Return all ``house_college`` positions for *election*, ordered."""
        return list(
            Position.objects.filter(
                election=election,
                category=Position.Category.HOUSE_COLLEGE,
            ).order_by("order", "title")
        )

    @staticmethod
    def compute_college_rep_audit(
        election: Election,
        *,
        positions: list[Position] | None = None,
        hash_to_voter: dict[str, EligibleVoter] | None = None,
    ) -> list[dict]:
        """
        Return a list of seat-report dicts, one per college-rep position.

        Each dict contains::

            {
                "election_id", "election_name",
                "position_id", "position_title", "allowed_college",
                "registered_voters",
                "total_raw_votes", "total_valid_votes", "total_invalid_votes",
                "unmatched_ballots", "valid_turnout_pct",
                "candidates": [ { "name", "raw_votes", "valid_votes", "invalid_votes" }, … ],
            }

        If *positions* or *hash_to_voter* are ``None`` they are computed
        automatically (callers may pass pre-built values for efficiency).
        """
        if positions is None:
            positions = CollegeRepAuditService.get_college_rep_positions(election)
        if hash_to_voter is None:
            hash_to_voter = CollegeRepAuditService.build_hash_to_voter(election)

        # Pre-count registered voters per normalised college
        college_voter_counts: dict[str, int] = defaultdict(int)
        college_display: dict[str, str] = {}
        for ev in hash_to_voter.values():
            norm = normalize_college(ev.college_snapshot)
            college_voter_counts[norm] += 1
            college_display[norm] = ev.college_snapshot

        report: list[dict] = []
        warnings: list[str] = []

        for pos in positions:
            raw_college = resolve_position_scope_college(pos)
            if not raw_college:
                warnings.append(
                    f"Could not resolve college scope for position: '{pos.title}'"
                )
                continue

            norm_allowed = normalize_college(raw_college)
            display_college = college_display.get(
                norm_allowed, f"College of {raw_college}"
            )
            registered = college_voter_counts.get(norm_allowed, 0)

            selections = (
                BallotSelection.objects
                .filter(position=pos)
                .select_related("ballot", "candidate")
            )

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
                    cand_invalid[cid] += 1
                    total_invalid += 1
                    continue

                voter_norm = normalize_college(voter.college_snapshot)
                if voter_norm == norm_allowed:
                    cand_valid[cid] += 1
                    total_valid += 1
                else:
                    cand_invalid[cid] += 1
                    total_invalid += 1

            turnout = (
                (total_valid / registered * 100) if registered > 0 else 0.0
            )

            candidates = []
            for cid, name in sorted(
                cand_names.items(),
                key=lambda kv: cand_valid.get(kv[0], 0),
                reverse=True,
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
