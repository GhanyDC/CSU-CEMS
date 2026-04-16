"""
Elections models — Election, Position, Candidate, EligibleVoter, VerificationRecord,
and RegistrarImportBatch.

Models are structured to match the campus constitutional structure:
  Executive Branch : President, Vice President
  Senate           : up to 12 Senators
  House            : College Representatives + Party-List Representatives

College elections mirror the campus pattern within a single college.
"""
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.elections.constants import OFFICIAL_COLLEGES


def candidate_photo_path(instance, filename):
    """Generate upload path for candidate photos using UUID to prevent path traversal."""
    return f"candidate_photos/{instance.position.election_id}/{uuid.uuid4().hex}.jpg"


class College(models.Model):
    """
    An official college that can participate in elections.

    Managed by admins via the admin panel. The name must match the college
    field on Student and Election records.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Short code or abbreviation (optional).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive colleges are hidden from election creation dropdowns.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "College"
        verbose_name_plural = "Colleges"

    def __str__(self) -> str:
        return self.name


class RegistrarImportBatch(models.Model):
    """
    System-level registrar import batch representing a school-year dataset.

    Reusable across elections. Each election references a batch to determine
    which registrar dataset to match verification records against.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        help_text="Descriptive name, e.g. 'AY 2025-2026 First Semester'.",
    )
    academic_year = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Academic year label, e.g. '2025-2026'.",
    )
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    total_imported = models.PositiveIntegerField(default=0)
    imported_by = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Registrar Import Batch"
        verbose_name_plural = "Registrar Import Batches"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class Election(models.Model):
    """Represents a discrete election event — campus-wide or per-college."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        PUBLISHED = "published", "Published"

    class ElectionType(models.TextChoices):
        CAMPUS = "campus", "Campus"
        COLLEGE = "college", "College"

    class VotingMode(models.TextChoices):
        ONLINE = "online", "Online"
        HYBRID = "hybrid", "Hybrid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    election_type = models.CharField(
        max_length=10,
        choices=ElectionType.choices,
        default=ElectionType.CAMPUS,
        db_index=True,
    )
    college = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Required for college elections. Must be an official college name.",
    )
    registrar_batch = models.ForeignKey(
        RegistrarImportBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="elections",
        help_text="The registrar import batch used for voter roll matching.",
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    voting_mode = models.CharField(
        max_length=10,
        choices=VotingMode.choices,
        default=VotingMode.ONLINE,
        db_index=True,
        help_text="Hybrid elections accept online ballots plus closed-period onsite canvass imports.",
    )
    banner = models.ImageField(
        upload_to="election_banners/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Optional banner image (JPG, PNG, or WebP, max 5 MB).",
    )
    voter_roll_finalized_at = models.DateTimeField(null=True, blank=True)
    voter_roll_finalized_by = models.CharField(max_length=255, blank=True, default="")
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
            models.CheckConstraint(
                condition=(
                    models.Q(election_type="campus", college="")
                    | models.Q(election_type="college") & ~models.Q(college="")
                ),
                name="college_required_for_college_elections",
            ),
        ]

    @property
    def is_campus(self) -> bool:
        return self.election_type == self.ElectionType.CAMPUS

    @property
    def is_college(self) -> bool:
        return self.election_type == self.ElectionType.COLLEGE

    @property
    def is_hybrid(self) -> bool:
        return self.voting_mode == self.VotingMode.HYBRID

    @property
    def is_voter_roll_finalized(self) -> bool:
        return self.voter_roll_finalized_at is not None

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    def clean(self) -> None:
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(
                {"end_time": "End time must be after start time."}
            )
        if self.election_type == self.ElectionType.COLLEGE:
            if not self.college:
                raise ValidationError(
                    {"college": "College is required for college elections."}
                )
            # Validate against the College table when populated; fall back to
            # the hard-coded constant list so tests and fresh installs still work.
            if College.objects.exists():
                if not College.objects.filter(name=self.college, is_active=True).exists():
                    raise ValidationError(
                        {"college": f"'{self.college}' is not a recognized active college."}
                    )
            else:
                if self.college not in OFFICIAL_COLLEGES:
                    raise ValidationError(
                        {"college": f"'{self.college}' is not a recognized official college."}
                    )
        elif self.election_type == self.ElectionType.CAMPUS:
            if self.college:
                raise ValidationError(
                    {"college": "Campus elections must not specify a college."}
                )


class Position(models.Model):
    """An elective position (seat) that appears on the ballot of a given election."""

    class Category(models.TextChoices):
        EXECUTIVE = "executive", "Executive"
        SENATE = "senate", "Senate"
        HOUSE_COLLEGE = "house_college", "House – College Representative"
        HOUSE_PARTY = "house_party", "House – Party-List Representative"
        COLLEGE_EXECUTIVE = "college_executive", "College Executive"
        COLLEGE_BOARD = "college_board", "College Board Member"

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
    photo = models.ImageField(
        upload_to=candidate_photo_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        help_text="Campaign/profile photo (max 2 MB, JPG/PNG/WebP).",
    )
    platform_text = models.TextField(
        blank=True,
        default="",
        help_text="Short candidate platform or description.",
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


class EligibleVoter(models.Model):
    """
    Per-election frozen voter roll entry.

    Created when registered students are matched against verification records.
    The college_snapshot preserves the student's college at the time of approval.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="voter_roll",
    )
    student = models.ForeignKey(
        "accounts.Student",
        on_delete=models.PROTECT,
        related_name="election_eligibility",
    )
    college_snapshot = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Eligible Voter"
        verbose_name_plural = "Eligible Voters"
        constraints = [
            models.UniqueConstraint(
                fields=["election", "student"],
                name="unique_voter_per_election",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} – {self.election.name}"


class VerificationRecord(models.Model):
    """
    Per-election verification form staging record.

    Imported from a verification form CSV and matched against the Student (registrar) table.
    """

    class MatchStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        MATCHED = "matched", "Matched"
        UNMATCHED = "unmatched", "Unmatched"
        DUPLICATE = "duplicate", "Duplicate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="verification_records",
    )
    student_id_input = models.CharField(max_length=50, db_index=True)
    full_name_input = models.CharField(max_length=255, blank=True, default="")
    college_input = models.CharField(max_length=255, blank=True, default="")
    matched_student = models.ForeignKey(
        "accounts.Student",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verification_records",
    )
    status = models.CharField(
        max_length=10,
        choices=MatchStatus.choices,
        default=MatchStatus.PENDING,
        db_index=True,
    )
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["imported_at"]
        verbose_name = "Verification Record"
        verbose_name_plural = "Verification Records"
        constraints = [
            models.UniqueConstraint(
                fields=["election", "student_id_input"],
                name="unique_verification_per_election",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id_input} – {self.election.name} ({self.get_status_display()})"


class HybridImportBatch(models.Model):
    """Audit-friendly batch record for onsite hybrid roster and tally imports."""

    class BatchType(models.TextChoices):
        ROSTER = "roster", "Onsite Roster"
        TALLY = "tally", "Onsite Tally"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUPERSEDED = "superseded", "Superseded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="hybrid_import_batches",
    )
    batch_type = models.CharField(
        max_length=10,
        choices=BatchType.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.FAILED,
        db_index=True,
    )
    source_filename = models.CharField(max_length=255, blank=True, default="")
    imported_by = models.CharField(max_length=255, blank=True, default="")
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    overlap_count = models.PositiveIntegerField(default=0)
    validation_summary = models.JSONField(default=dict, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hybrid Import Batch"
        verbose_name_plural = "Hybrid Import Batches"

    def __str__(self) -> str:
        return (
            f"{self.election.name} – {self.get_batch_type_display()} "
            f"({self.get_status_display()})"
        )


class OnsiteParticipation(models.Model):
    """One validated onsite voter participation row linked to a roster batch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        HybridImportBatch,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    student = models.ForeignKey(
        "accounts.Student",
        on_delete=models.PROTECT,
        related_name="onsite_participations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Onsite Participation"
        verbose_name_plural = "Onsite Participations"
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "student"],
                name="unique_onsite_participation_per_batch_student",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} – {self.batch.election.name}"


class OnsiteTally(models.Model):
    """Validated onsite tally row for a candidate within a hybrid tally batch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        HybridImportBatch,
        on_delete=models.CASCADE,
        related_name="tallies",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="onsite_tallies",
    )
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.PROTECT,
        related_name="onsite_tallies",
    )
    onsite_votes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position__order", "candidate__full_name"]
        verbose_name = "Onsite Tally"
        verbose_name_plural = "Onsite Tallies"
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "position", "candidate"],
                name="unique_onsite_tally_per_batch_position_candidate",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.batch.election.name} – {self.position.title} – "
            f"{self.candidate.full_name}"
        )
