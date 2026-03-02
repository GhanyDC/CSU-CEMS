"""
Voting models — Vote entity.

Votes store a hashed student_id (never the raw value) to preserve
ballot secrecy while still allowing one-person-one-vote enforcement.
"""
import hashlib
import uuid

from django.conf import settings
from django.db import models


class Vote(models.Model):
    """
    Immutable record of a single vote.

    The raw student_id is NEVER stored.  Instead we store a
    salted SHA-256 hash so that we can enforce one-person-one-vote
    without leaking which student voted for whom.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hashed_student_id: models.CharField = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of (student_id + secret salt).",
    )
    candidate: models.ForeignKey = models.ForeignKey(
        "elections.Candidate",
        on_delete=models.PROTECT,
        related_name="votes",
    )
    position: models.CharField = models.CharField(
        max_length=100,
        help_text="Position this vote is for.",
    )
    timestamp: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Vote"
        verbose_name_plural = "Votes"

    def __str__(self) -> str:
        return f"Vote {self.id} – {self.position}"

    @staticmethod
    def hash_student_id(student_id: str) -> str:
        """
        Return a salted SHA-256 hex digest of the student_id.

        Uses DJANGO SECRET_KEY as salt so the hash cannot be
        reversed without knowledge of the secret.
        """
        salt: str = settings.SECRET_KEY
        value: str = f"{salt}:{student_id}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
