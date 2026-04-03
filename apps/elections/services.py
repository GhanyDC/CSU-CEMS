"""
Election services — lifecycle management and result computation.
"""
import logging
from collections import defaultdict

from django.db import models, transaction
from django.db.models import Count

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import BallotSelection

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

        if category == Position.Category.EXECUTIVE:
            return ResultService._executive_rule(results, total_votes)

        if category == Position.Category.SENATE:
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
