"""
Election services — lifecycle management, result computation, and voter roll management.
"""
import logging
from collections import defaultdict

from django.db import models, transaction
from django.db.models import Count
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    VerificationRecord,
)
from apps.voting.models import Ballot, BallotSelection

logger = logging.getLogger("cems.application")


class InvalidTransitionError(Exception):
    """Raised when an election status transition is not allowed."""


class ElectionNotReadyError(Exception):
    """Raised when an election cannot be published (e.g. not closed)."""


# ---------------------------------------------------------------------------
# Election Lifecycle
# ---------------------------------------------------------------------------

class ElectionLifecycleService:
    """
    Manages the election state machine:
        DRAFT → ACTIVE → CLOSED → PUBLISHED

    Each transition is validated and audit-logged.
    """

    # Valid transitions: current_status → next_status
    _TRANSITIONS = {
        Election.Status.DRAFT: Election.Status.ACTIVE,
        Election.Status.ACTIVE: Election.Status.CLOSED,
        Election.Status.CLOSED: Election.Status.PUBLISHED,
    }

    _AUDIT_EVENTS = {
        Election.Status.ACTIVE: AuditLog.EventType.ELECTION_STARTED,
        Election.Status.CLOSED: AuditLog.EventType.ELECTION_CLOSED,
        Election.Status.PUBLISHED: AuditLog.EventType.RESULTS_PUBLISHED,
    }

    @classmethod
    @transaction.atomic
    def transition(
        cls,
        election: Election,
        target_status: str,
        *,
        performed_by: str = "system",
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> Election:
        """
        Advance an election to the next valid status.

        Uses select_for_update to prevent concurrent transitions.

        Args:
            election:       The Election instance to transition.
            target_status:  The desired new status value.
            performed_by:   Identifier for the actor (admin student_id or "system").
            ip_address:     Optional client IP for audit.
            user_agent:     Optional UA for audit.

        Returns:
            The updated Election instance.

        Raises:
            InvalidTransitionError: If the transition is not valid.
        """
        # Lock the election row to prevent race conditions
        election = Election.objects.select_for_update().get(pk=election.pk)

        allowed_next = cls._TRANSITIONS.get(election.status)

        if allowed_next is None or allowed_next != target_status:
            raise InvalidTransitionError(
                f"Cannot transition election from '{election.get_status_display()}' "
                f"to '{target_status}'. "
                f"Allowed next status: {allowed_next or 'none (terminal state)'}."
            )

        old_status = election.status
        election.status = target_status
        election.save(update_fields=["status", "updated_at"])

        # Audit log
        event_type = cls._AUDIT_EVENTS.get(target_status)
        if event_type:
            AuditService.log_event(
                student_id_attempted=performed_by,
                event_type=event_type,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
                details=(
                    f"Election '{election.name}' ({election.pk}) "
                    f"transitioned from {old_status} to {target_status}."
                ),
            )

        logger.info(
            "Election lifecycle transition: election_id=%s, %s → %s, by=%s",
            election.pk, old_status, target_status, performed_by,
        )
        return election

    @classmethod
    def start_election(cls, election: Election, **kwargs) -> Election:
        # Voter roll must be finalized before starting (only check for valid transition)
        fresh = Election.objects.get(pk=election.pk)
        if fresh.status == Election.Status.DRAFT and not fresh.is_voter_roll_finalized:
            raise ElectionNotReadyError(
                "Cannot start election: voter roll has not been finalized."
            )
        return cls.transition(election, Election.Status.ACTIVE, **kwargs)

    @classmethod
    def close_election(cls, election: Election, **kwargs) -> Election:
        return cls.transition(election, Election.Status.CLOSED, **kwargs)

    @classmethod
    def publish_results(cls, election: Election, **kwargs) -> Election:
        return cls.transition(election, Election.Status.PUBLISHED, **kwargs)


# ---------------------------------------------------------------------------
# Result Computation
# ---------------------------------------------------------------------------

class ResultService:
    """
    Computes election results from BallotSelection records.

    Rules by position category:
    - EXECUTIVE:     Majority required (50% + 1). If no majority → "no_majority".
    - SENATE:        Top N candidates win (N = position.max_selections).
    - HOUSE_COLLEGE: Plurality (highest votes wins).
    - HOUSE_PARTY:   Plurality (highest votes wins).
    """

    @staticmethod
    def compute_results(election: Election) -> dict:
        """
        Compute structured results for a published election.

        Returns:
            A dict with the structure:
            {
                "election_id": "...",
                "election_name": "...",
                "positions": [
                    {
                        "position_id": "...",
                        "position": "President",
                        "category": "executive",
                        "total_votes": 1200,
                        "max_selections": 1,
                        "winner": "..." | null,
                        "status": "won" | "no_majority",
                        "results": [
                            {"candidate_id": "...", "candidate": "...", "party": "...", "votes": 650},
                        ]
                    },
                ]
            }
        """
        positions = (
            Position.objects.filter(election=election)
            .order_by("order", "title")
        )

        positions_data = []
        for position in positions:
            position_result = ResultService._compute_position_result(position)
            positions_data.append(position_result)

        return {
            "election_id": str(election.pk),
            "election_name": election.name,
            "positions": positions_data,
        }

    @staticmethod
    def _compute_position_result(position: Position) -> dict:
        """Compute results for a single position."""
        # Count votes per candidate via DB aggregation
        vote_counts = (
            BallotSelection.objects
            .filter(position=position)
            .values("candidate__id", "candidate__full_name", "candidate__party")
            .annotate(votes=Count("id"))
            .order_by("-votes")
        )

        results = [
            {
                "candidate_id": str(row["candidate__id"]),
                "candidate": row["candidate__full_name"],
                "party": row["candidate__party"],
                "votes": row["votes"],
            }
            for row in vote_counts
        ]

        # Include candidates with zero votes
        voted_ids = {r["candidate_id"] for r in results}
        zero_vote_candidates = (
            Candidate.objects
            .filter(position=position, is_active=True)
            .exclude(pk__in=voted_ids)
            .order_by("full_name")
        )
        for c in zero_vote_candidates:
            results.append(
                {
                    "candidate_id": str(c.pk),
                    "candidate": c.full_name,
                    "party": c.party,
                    "votes": 0,
                }
            )

        total_votes = sum(r["votes"] for r in results)

        # Determine winner(s) based on category
        winner, status = ResultService._determine_winner(
            position, results, total_votes,
        )

        return {
            "position_id": str(position.pk),
            "position": position.title,
            "category": position.category,
            "total_votes": total_votes,
            "max_selections": position.max_selections,
            "winner": winner,
            "status": status,
            "results": results,
        }

    @staticmethod
    def _determine_winner(
        position: Position,
        results: list[dict],
        total_votes: int,
    ) -> tuple[str | list[str] | None, str]:
        """
        Apply the appropriate winning rule for this position's category.

        Returns:
            (winner, status) where:
            - winner is a name string, list of names, or None
            - status is "won", "no_majority", or "no_votes"
        """
        if total_votes == 0:
            return None, "no_votes"

        category = position.category

        if category in (
            Position.Category.EXECUTIVE,
            Position.Category.COLLEGE_EXECUTIVE,
        ):
            return ResultService._executive_rule(results, total_votes)

        if category in (
            Position.Category.SENATE,
            Position.Category.COLLEGE_BOARD,
        ):
            return ResultService._multi_seat_rule(results, position.max_selections)

        # HOUSE_COLLEGE and HOUSE_PARTY: single-seat plurality
        return ResultService._plurality_rule(results)

    @staticmethod
    def _executive_rule(
        results: list[dict], total_votes: int,
    ) -> tuple[str | None, str]:
        """
        Executive positions require an absolute majority (50% + 1).
        """
        majority_threshold = (total_votes // 2) + 1

        if results and results[0]["votes"] >= majority_threshold:
            return results[0]["candidate"], "won"

        return None, "no_majority"

    @staticmethod
    def _multi_seat_rule(
        results: list[dict], seats: int,
    ) -> tuple[list[str], str]:
        """
        Multi-seat positions (Senate): top N candidates by vote count win.
        """
        winners = [r["candidate"] for r in results[:seats] if r["votes"] > 0]
        return winners, "won"

    @staticmethod
    def _plurality_rule(results: list[dict]) -> tuple[str | None, str]:
        """
        Single-seat plurality: candidate with most votes wins.
        """
        if results and results[0]["votes"] > 0:
            return results[0]["candidate"], "won"
        return None, "no_votes"

    @staticmethod
    def compute_results_with_thresholds(election: Election) -> dict:
        """
        Like compute_results but adds 50%+1 threshold info per position.

        Threshold denominator rules (from KNOWN_DECISIONS_COMPACT):
        - Campus positions: total approved campus voter roll
        - College election positions: approved voter roll of that college election
        - College Representatives in campus election: approved voters of represented college
        """
        base = ResultService.compute_results(election)

        # Get total eligible voter count
        total_eligible = EligibleVoter.objects.filter(election=election).count()
        total_ballots = Ballot.objects.filter(election=election).count()

        # For campus elections, also get per-college counts
        college_counts = {}
        if election.is_campus:
            college_counts = {
                row["college_snapshot"]: row["count"]
                for row in (
                    EligibleVoter.objects
                    .filter(election=election)
                    .values("college_snapshot")
                    .annotate(count=Count("id"))
                )
            }

        for pos_data in base["positions"]:
            # Determine the right denominator for 50%+1
            category = pos_data["category"]
            if category == Position.Category.HOUSE_COLLEGE:
                # College rep in campus election: denominator = voters of that college
                # Extract college name from position title
                pos_obj = Position.objects.get(pk=pos_data["position_id"])
                college_name = ""
                if pos_obj.title.startswith("College Representative"):
                    # title format: "College Representative – ShortName"
                    parts = pos_obj.title.split("–")
                    if len(parts) > 1:
                        short = parts[1].strip()
                        # Find the official college matching this short name
                        from apps.elections.constants import OFFICIAL_COLLEGES
                        for oc in OFFICIAL_COLLEGES:
                            if oc.replace("College of ", "") == short or oc == short:
                                college_name = oc
                                break
                denominator = college_counts.get(college_name, 0)
            else:
                denominator = total_eligible

            threshold = (denominator // 2) + 1 if denominator > 0 else 0
            pos_data["threshold_denominator"] = denominator
            pos_data["threshold_50_plus_1"] = threshold

        base["total_eligible"] = total_eligible
        base["total_ballots"] = total_ballots
        base["turnout_percentage"] = round(
            (total_ballots / total_eligible * 100) if total_eligible > 0 else 0, 2
        )
        return base


# ---------------------------------------------------------------------------
# Turnout Service
# ---------------------------------------------------------------------------

class TurnoutService:
    """
    Provides turnout/progress data for monitoring during active elections.
    Does NOT expose per-candidate tallies.
    """

    @staticmethod
    def compute_turnout(election: Election) -> dict:
        """
        Return turnout statistics for an election.

        Returns:
            {
                "election_id": "...",
                "election_name": "...",
                "status": "...",
                "total_eligible": int,
                "total_voted": int,
                "turnout_percentage": float,
                "by_college": [
                    {"college": "...", "eligible": int, "voted": int, "percentage": float},
                    ...
                ],
            }
        """
        total_eligible = EligibleVoter.objects.filter(election=election).count()
        total_voted = Ballot.objects.filter(election=election).count()

        # Per-college breakdown from voter roll
        college_eligible = (
            EligibleVoter.objects
            .filter(election=election)
            .values("college_snapshot")
            .annotate(count=Count("id"))
        )
        eligible_by_college = {
            row["college_snapshot"]: row["count"] for row in college_eligible
        }

        # Per-college ballot counts require joining through hashed IDs
        # Since we can't directly join, count ballots per election and compute
        # We use the total as the top-level metric; per-college for eligible only
        # (per-college voted is complex due to hashing; we report eligible per college)
        college_data = []
        for college_name, eligible_count in sorted(eligible_by_college.items()):
            if not college_name:
                continue
            college_data.append({
                "college": college_name,
                "eligible": eligible_count,
            })

        return {
            "election_id": str(election.pk),
            "election_name": election.name,
            "election_type": election.election_type,
            "status": election.status,
            "total_eligible": total_eligible,
            "total_voted": total_voted,
            "turnout_percentage": round(
                (total_voted / total_eligible * 100) if total_eligible > 0 else 0, 2
            ),
            "by_college": college_data,
        }


# ---------------------------------------------------------------------------
# Voter Roll Management
# ---------------------------------------------------------------------------

class VoterRollError(Exception):
    """Raised for voter-roll pipeline errors."""


class VoterRollService:
    """
    Manages the per-election voter roll lifecycle:
      1. Import verification form CSV rows
      2. Match against the registrar (Student table)
      3. Generate EligibleVoter records from matched entries
      4. Finalize the voter roll (locks it)
    """

    @staticmethod
    @transaction.atomic
    def import_verification(
        election: Election,
        rows: list[dict],
    ) -> dict:
        """
        Import verification form rows for an election.

        Args:
            election: The election to import verification records for.
            rows: List of dicts with keys: student_id, full_name (optional), college (optional).

        Returns:
            Summary dict: {created, skipped_duplicate, matched, unmatched}.
        """
        from apps.accounts.models import Student

        if election.is_voter_roll_finalized:
            raise VoterRollError("Cannot import: voter roll is already finalized.")

        # Pre-load existing student IDs from the registrar for fast lookup
        student_map = {
            s.student_id: s
            for s in Student.objects.all().only("pk", "student_id")
        }

        # Pre-load already-imported student_id_input values for this election
        existing_ids = set(
            VerificationRecord.objects
            .filter(election=election)
            .values_list("student_id_input", flat=True)
        )

        created = 0
        skipped_duplicate = 0
        matched = 0
        unmatched = 0

        records_to_create = []
        for row in rows:
            sid = row.get("student_id", "").strip()
            if not sid:
                continue

            if sid in existing_ids:
                skipped_duplicate += 1
                continue

            existing_ids.add(sid)
            student = student_map.get(sid)

            if student:
                status = VerificationRecord.MatchStatus.MATCHED
                matched += 1
            else:
                status = VerificationRecord.MatchStatus.UNMATCHED
                unmatched += 1

            records_to_create.append(VerificationRecord(
                election=election,
                student_id_input=sid,
                full_name_input=row.get("full_name", "").strip(),
                college_input=row.get("college", "").strip(),
                matched_student=student,
                status=status,
            ))
            created += 1

        if records_to_create:
            VerificationRecord.objects.bulk_create(records_to_create)

        logger.info(
            "Verification import: election=%s, created=%d, skipped=%d, matched=%d, unmatched=%d",
            election.pk, created, skipped_duplicate, matched, unmatched,
        )

        return {
            "created": created,
            "skipped_duplicate": skipped_duplicate,
            "matched": matched,
            "unmatched": unmatched,
        }

    @staticmethod
    def get_match_summary(election: Election) -> dict:
        """Return counts of verification records by status."""
        counts = (
            VerificationRecord.objects
            .filter(election=election)
            .values("status")
            .annotate(count=Count("id"))
        )
        summary = {
            "total": 0,
            "matched": 0,
            "unmatched": 0,
            "duplicate": 0,
            "pending": 0,
        }
        for row in counts:
            summary[row["status"]] = row["count"]
            summary["total"] += row["count"]
        return summary

    @staticmethod
    def get_unmatched_records(election: Election):
        """Return queryset of unmatched verification records."""
        return VerificationRecord.objects.filter(
            election=election,
            status=VerificationRecord.MatchStatus.UNMATCHED,
        )

    @staticmethod
    @transaction.atomic
    def generate_voter_roll(election: Election) -> int:
        """
        Create EligibleVoter records from MATCHED verification records.

        For college elections, only students whose college matches the
        election's college are included.

        Returns the number of EligibleVoter records created.
        """
        if election.is_voter_roll_finalized:
            raise VoterRollError("Cannot generate: voter roll is already finalized.")

        matched_records = VerificationRecord.objects.filter(
            election=election,
            status=VerificationRecord.MatchStatus.MATCHED,
            matched_student__isnull=False,
        ).select_related("matched_student")

        # Filter already-enrolled voters
        existing_student_ids = set(
            EligibleVoter.objects
            .filter(election=election)
            .values_list("student_id", flat=True)
        )

        voters_to_create = []
        for record in matched_records:
            student = record.matched_student
            if student.pk in existing_student_ids:
                continue

            # For college elections, only include students from the matching college
            if election.is_college and student.college != election.college:
                continue

            voters_to_create.append(EligibleVoter(
                election=election,
                student=student,
                college_snapshot=student.college or "",
            ))
            existing_student_ids.add(student.pk)

        if voters_to_create:
            EligibleVoter.objects.bulk_create(voters_to_create)

        logger.info(
            "Voter roll generated: election=%s, created=%d",
            election.pk, len(voters_to_create),
        )
        return len(voters_to_create)

    @staticmethod
    @transaction.atomic
    def finalize_voter_roll(
        election: Election,
        finalized_by: str,
    ) -> None:
        """
        Lock the voter roll for an election.

        After finalization, no more EligibleVoter records can be added or removed.
        """
        election = Election.objects.select_for_update().get(pk=election.pk)

        if election.is_voter_roll_finalized:
            raise VoterRollError("Voter roll is already finalized.")

        if not EligibleVoter.objects.filter(election=election).exists():
            raise VoterRollError("Cannot finalize an empty voter roll.")

        election.voter_roll_finalized_at = timezone.now()
        election.voter_roll_finalized_by = finalized_by
        election.save(update_fields=[
            "voter_roll_finalized_at",
            "voter_roll_finalized_by",
            "updated_at",
        ])

        logger.info(
            "Voter roll finalized: election=%s, by=%s, count=%d",
            election.pk, finalized_by,
            EligibleVoter.objects.filter(election=election).count(),
        )

    @staticmethod
    def get_approved_count(election: Election) -> int:
        """Return the total number of eligible voters for an election."""
        return EligibleVoter.objects.filter(election=election).count()

    @staticmethod
    def get_approved_count_by_college(election: Election) -> dict[str, int]:
        """Return eligible voter counts grouped by college_snapshot."""
        counts = (
            EligibleVoter.objects
            .filter(election=election)
            .values("college_snapshot")
            .annotate(count=Count("id"))
        )
        return {row["college_snapshot"]: row["count"] for row in counts}
