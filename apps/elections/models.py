"""
Elections models — Election, Position, and Candidate entities.

Models are structured to match the campus constitutional structure:
  Executive Branch : President, Vice President
  Senate           : up to 12 Senators
  House            : College Representatives + Party-List Representatives
"""
import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Election(models.Model):
    """Represents a discrete campus election event (e.g. Academic Year 2026 General Elections)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        PUBLISHED = "published", "Published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_time"]
        verbose_name = "Election"
        verbose_name_plural = "Elections"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="election_end_time_after_start_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    def clean(self) -> None:
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(
                {"end_time": "End time must be after start time."}
            )


class Position(models.Model):
    """An elective position (seat) that appears on the ballot of a given election."""

    class Category(models.TextChoices):
        EXECUTIVE = "executive", "Executive"
        SENATE = "senate", "Senate"
        HOUSE_COLLEGE = "house_college", "House – College Representative"
        HOUSE_PARTY = "house_party", "House – Party-List Representative"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    title = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        db_index=True,
    )
    max_selections = models.PositiveSmallIntegerField(
        default=1,
        help_text="Maximum number of candidates a voter may select for this position.",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Ascending display order on the ballot.",
    )

    class Meta:
        ordering = ["order", "title"]
        verbose_name = "Position"
        verbose_name_plural = "Positions"
        constraints = [
            models.UniqueConstraint(
                fields=["election", "title"],
                name="unique_position_title_per_election",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.election.name})"


class Candidate(models.Model):
    """Represents a candidate contesting a specific position in an election."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    full_name = models.CharField(max_length=255)
    party = models.CharField(max_length=100, blank=True, default="")
    college = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="College affiliation — required for House College Representatives.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position__order", "full_name"]
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"
        constraints = [
            models.UniqueConstraint(
                fields=["position", "full_name"],
                name="unique_candidate_name_per_position",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} – {self.position.title}"

    def clean(self) -> None:
        super().clean()
        if (
            self.position_id
            and hasattr(self, "position")
            and self.position.category == Position.Category.HOUSE_COLLEGE
            and not self.college
        ):
            raise ValidationError(
                {"college": "College is required for House College Representatives."}
            )
