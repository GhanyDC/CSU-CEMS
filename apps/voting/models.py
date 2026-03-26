"""
Voting models — Ballot and BallotSelection entities.

A Ballot is the top-level immutable receipt that ties a hashed student
identity to exactly one participation per election.  Each BallotSelection
records one candidate choice within that ballot.

The raw student_id is NEVER persisted.  Only a salted SHA-256 digest is
stored so that one-ballot-per-voter enforcement is possible without
revealing which student cast which ballot (vote secrecy).
"""
import hashlib
import uuid

from django.conf import settings
from django.db import models


class Ballot(models.Model):
    """
    Immutable top-level record of a student's participation in an election.

    The unique constraint on (election, hashed_student_id) enforces
    one ballot per voter per election at the database level.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    election = models.ForeignKey(
        "elections.Election",
        on_delete=models.PROTECT,
        related_name="ballots",
    )
    hashed_student_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of (student_id + SECRET_KEY salt).",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Ballot"
        verbose_name_plural = "Ballots"
        constraints = [
            models.UniqueConstraint(
                fields=["election", "hashed_student_id"],
                name="unique_ballot_per_voter_per_election",
            )
        ]

    def __str__(self) -> str:
        return f"Ballot {self.id} – {self.election.name}"

    @staticmethod
    def hash_student_id(student_id: str, election_id: str = "") -> str:
        """
        Return a salted SHA-256 hex digest of the student_id scoped to an election.

        Uses DJANGO SECRET_KEY as salt so the hash cannot be
        reversed without knowledge of the secret.
        Including the election_id ensures that hashes are unique per election
        cycle, preventing cross-election correlation of voter identity.
        """
        salt: str = settings.SECRET_KEY
        value: str = f"{salt}:{student_id}:{election_id}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class BallotSelection(models.Model):
    """
    A single candidate selection within a ballot.

    The unique constraint on (ballot, position, candidate) prevents duplicate
    selections and is enforced at the database level.  The position FK allows
    efficient per-position aggregation (vote tallying) without joining through Ballot.
    """

    ballot = models.ForeignKey(
        Ballot,
        on_delete=models.CASCADE,
        related_name="selections",
    )
    position = models.ForeignKey(
        "elections.Position",
        on_delete=models.PROTECT,
        related_name="ballot_selections",
    )
    candidate = models.ForeignKey(
        "elections.Candidate",
        on_delete=models.PROTECT,
        related_name="ballot_selections",
    )

    class Meta:
        verbose_name = "Ballot Selection"
        verbose_name_plural = "Ballot Selections"
        constraints = [
            models.UniqueConstraint(
                fields=["ballot", "position", "candidate"],
                name="unique_selection_per_ballot_position_candidate",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.ballot_id} → {self.position.title}: {self.candidate.full_name}"
        )
