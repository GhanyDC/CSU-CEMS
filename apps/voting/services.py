"""
Voting service — transactional vote creation with integrity checks.
"""
import logging
from typing import Optional

from django.db import transaction

from apps.accounts.models import Student
from apps.elections.models import Candidate
from apps.voting.models import Vote

logger = logging.getLogger("cems.application")


class VoteAlreadyCastError(Exception):
    """Raised when a student attempts to vote more than once."""

    pass


class VotingService:
    """
    Encapsulates voting business logic with transactional integrity.
    """

    @staticmethod
    @transaction.atomic
    def cast_vote(student: Student, candidate: Candidate) -> Vote:
        """
        Atomically record a vote.

        1. Lock the student row (SELECT … FOR UPDATE) to prevent races.
        2. Verify the student has not already voted.
        3. Create the Vote with a hashed student_id.
        4. Mark the student as having voted.

        Raises VoteAlreadyCastError if the student already voted.
        """
        # Lock row to prevent concurrent double-vote
        locked_student: Student = (
            Student.objects.select_for_update().get(pk=student.pk)
        )

        if locked_student.has_voted:
            logger.warning(
                "Double vote attempt blocked for student_id=%s",
                locked_student.student_id,
            )
            raise VoteAlreadyCastError("This student has already voted.")

        hashed_id: str = Vote.hash_student_id(locked_student.student_id)

        # Additional check: ensure no vote with this hash exists
        if Vote.objects.filter(hashed_student_id=hashed_id).exists():
            logger.warning(
                "Hashed student_id collision detected for student_id=%s",
                locked_student.student_id,
            )
            raise VoteAlreadyCastError("Vote record already exists for this student.")

        vote: Vote = Vote.objects.create(
            hashed_student_id=hashed_id,
            candidate=candidate,
            position=candidate.position,
        )

        locked_student.has_voted = True
        locked_student.save(update_fields=["has_voted"])

        logger.info(
            "Vote cast successfully: vote_id=%s, position=%s",
            vote.id,
            vote.position,
        )
        return vote
