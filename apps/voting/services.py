"""
Voting service — transactional ballot creation with integrity checks.
"""
import logging

from django.db import transaction

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position
from apps.voting.models import Ballot, BallotSelection

logger = logging.getLogger("cems.application")


class BallotAlreadyCastError(Exception):
    """Raised when a student attempts to vote in the same election more than once."""

    pass


class VotingService:
    """
    Encapsulates ballot casting business logic with transactional integrity.
    """

    @staticmethod
    @transaction.atomic
    def cast_ballot(
        student: Student,
        election: Election,
        selections: list[tuple[Position, Candidate]],
    ) -> Ballot:
        """
        Atomically record a full ballot with all its candidate selections.

        Steps:
        1. Lock the student row (SELECT … FOR UPDATE) to prevent race conditions.
        2. Derive the hashed student ID and verify no ballot exists for this
           (election, hash) pair — enforced both in Python and by the DB constraint.
        3. Create the Ballot record.
        4. Create one BallotSelection per (position, candidate) pair.
        5. Mark the student as having voted.

        Args:
            student:    The authenticated Student instance.
            election:   The active Election being voted in.
            selections: A list of (Position, Candidate) tuples — one tuple per
                        position the student wishes to cast a vote for.

        Returns:
            The newly created Ballot instance.

        Raises:
            BallotAlreadyCastError: If this student has already submitted a
                ballot for this election.
        """
        locked_student: Student = (
            Student.objects.select_for_update().get(pk=student.pk)
        )

        hashed_id: str = Ballot.hash_student_id(locked_student.student_id)

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

        ballot: Ballot = Ballot.objects.create(
            election=election,
            hashed_student_id=hashed_id,
        )

        for position, candidate in selections:
            BallotSelection.objects.create(
                ballot=ballot,
                position=position,
                candidate=candidate,
            )

        locked_student.has_voted = True
        locked_student.save(update_fields=["has_voted"])

        logger.info(
            "Ballot cast successfully: ballot_id=%s, election_id=%s, selections=%d",
            ballot.id,
            election.pk,
            len(selections),
        )
        return ballot
