"""
Voting service — transactional ballot creation with integrity checks.
"""
import logging
from collections import Counter

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Student
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import Ballot, BallotSelection

logger = logging.getLogger("cems.application")


class BallotAlreadyCastError(Exception):
    """Raised when a student attempts to vote in the same election more than once."""


class ElectionNotActiveError(Exception):
    """Raised when an election is not currently accepting ballots."""


class InvalidSelectionError(Exception):
    """Raised when ballot selections fail validation."""


class BallotService:
    """
    Encapsulates ballot casting business logic with transactional integrity.
    """

    @staticmethod
    def cast_ballot(
        student: Student,
        election: Election,
        selections: list[tuple[str, str]],
        *,
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> Ballot:
        """
        Atomically record a full ballot with all its candidate selections.

        Args:
            student:    The authenticated Student instance.
            election:   The Election being voted in.
            selections: A list of (position_id, candidate_id) string tuples.
            ip_address: Optional client IP for audit logging.
            user_agent: Optional UA string for audit logging.

        Returns:
            The newly created Ballot instance.

        Raises:
            ElectionNotActiveError: If the election is not active or outside its window.
            BallotAlreadyCastError: If this student has already submitted a ballot.
            InvalidSelectionError:  If selections fail validation.
        """
        # 1. Validate election is active and within its time window
        now = timezone.now()
        if election.status != Election.Status.ACTIVE:
            raise ElectionNotActiveError("This election is not currently active.")
        if now < election.start_time or now > election.end_time:
            raise ElectionNotActiveError(
                "This election is not within its voting window."
            )

        # 2. Validate selections list is non-empty
        if not selections:
            raise InvalidSelectionError("At least one selection is required.")

        try:
            return BallotService._cast_ballot_atomic(
                student, election, selections,
                ip_address=ip_address, user_agent=user_agent,
            )
        except BallotAlreadyCastError:
            # Log suspicious activity OUTSIDE the rolled-back transaction
            AuditService.log_event(
                student_id_attempted=student.student_id,
                event_type=AuditLog.EventType.SUSPICIOUS_ACTIVITY,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                details=f"Duplicate ballot attempt for election {election.pk}.",
            )
            raise

    @staticmethod
    @transaction.atomic
    def _cast_ballot_atomic(
        student: Student,
        election: Election,
        selections: list[tuple[str, str]],
        *,
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> Ballot:
        """Inner atomic method that performs the actual ballot creation."""
        # 3. Lock the student row to prevent race conditions
        locked_student: Student = (
            Student.objects.select_for_update().get(pk=student.pk)
        )

        # 4. Generate election-scoped hashed student ID
        hashed_id: str = Ballot.hash_student_id(
            locked_student.student_id, str(election.pk)
        )

        # 5. Check for existing ballot (Python-level check before DB constraint)
        if Ballot.objects.filter(
            election=election, hashed_student_id=hashed_id
        ).exists():
            logger.warning(
                "Duplicate ballot attempt blocked: election_id=%s",
                election.pk,
            )
            raise BallotAlreadyCastError(
                "A ballot has already been submitted for this election."
            )

        # 6. Validate all selections
        positions_for_election = {
            str(p.pk): p
            for p in Position.objects.filter(election=election)
        }

        resolved_selections: list[tuple[Position, Candidate]] = []
        selection_counts: Counter = Counter()

        for position_id, candidate_id in selections:
            # Position must belong to this election
            position = positions_for_election.get(position_id)
            if position is None:
                raise InvalidSelectionError(
                    f"Position '{position_id}' does not belong to this election."
                )

            selection_counts[position_id] += 1
            if selection_counts[position_id] > position.max_selections:
                raise InvalidSelectionError(
                    f"Too many selections for position '{position.title}'. "
                    f"Maximum allowed: {position.max_selections}."
                )

            # Candidate must belong to position and be active
            try:
                candidate = Candidate.objects.get(
                    pk=candidate_id, position=position, is_active=True
                )
            except Candidate.DoesNotExist:
                raise InvalidSelectionError(
                    f"Candidate '{candidate_id}' is not a valid active "
                    f"candidate for position '{position.title}'."
                )

            resolved_selections.append((position, candidate))

        # 7. Check for duplicate (position, candidate) pairs
        selection_pairs = [(str(p.pk), str(c.pk)) for p, c in resolved_selections]
        if len(selection_pairs) != len(set(selection_pairs)):
            raise InvalidSelectionError(
                "Duplicate candidate selections are not allowed."
            )

        # 8. Create Ballot
        try:
            ballot: Ballot = Ballot.objects.create(
                election=election,
                hashed_student_id=hashed_id,
            )
        except IntegrityError:
            raise BallotAlreadyCastError(
                "A ballot has already been submitted for this election."
            )

        # 9. Create BallotSelections in bulk
        ballot_selections = [
            BallotSelection(ballot=ballot, position=pos, candidate=cand)
            for pos, cand in resolved_selections
        ]
        BallotSelection.objects.bulk_create(ballot_selections)

        # 10. Mark student as having voted
        locked_student.has_voted = True
        locked_student.save(update_fields=["has_voted"])

        # 11. Audit log
        AuditService.log_event(
            student_id_attempted=locked_student.student_id,
            event_type=AuditLog.EventType.VOTE_CAST,
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
            details=(
                f"Ballot {ballot.pk} cast for election {election.pk} "
                f"with {len(resolved_selections)} selection(s)."
            ),
        )

        logger.info(
            "Ballot cast successfully: ballot_id=%s, election_id=%s, selections=%d",
            ballot.id,
            election.pk,
            len(resolved_selections),
        )
        return ballot


# Backward compatibility alias
VotingService = BallotService
