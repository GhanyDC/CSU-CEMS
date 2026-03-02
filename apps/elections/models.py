"""
Elections models — Candidate entity.
"""
import uuid

from django.db import models


class Candidate(models.Model):
    """
    Represents a candidate standing for a specific position.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    full_name: models.CharField = models.CharField(max_length=255)
    position: models.CharField = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Position the candidate is contesting (e.g. President).",
    )
    party: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "full_name"]
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.position})"
