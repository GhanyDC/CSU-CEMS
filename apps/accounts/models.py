"""
Accounts models — Student entity and Admin profile.

The Student model is the core identity model for voters.
It is intentionally NOT a Django User model because authentication
happens via student_id + date_of_birth, not username/password.

The AdminProfile model links to Django's built-in User model and adds
role-based access control for election officers. Admin authentication
is completely separate from student authentication.
"""
import uuid
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.db import models
from django.utils import timezone


class Student(models.Model):
    """
    Represents an enrolled student eligible to vote.

    Authentication is via student_id + date_of_birth.
    Account locks after CEMS_MAX_FAILED_ATTEMPTS failed login attempts.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    student_id: models.CharField = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique student identifier (e.g. matric number).",
    )
    full_name: models.CharField = models.CharField(max_length=255)
    date_of_birth: models.DateField = models.DateField()
    college: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="College affiliation (e.g. College of Engineering).",
    )
    course: models.CharField = models.CharField(max_length=255)
    year: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField()
    is_admin: models.BooleanField = models.BooleanField(
        default=False,
        help_text="Designates whether this student has admin privileges.",
    )
    failed_attempts: models.PositiveIntegerField = models.PositiveIntegerField(
        default=0,
    )
    lock_until: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Account locked until this time after exceeding failed attempts.",
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student_id"]
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self) -> str:
        return f"{self.student_id} – {self.full_name}"

    @property
    def is_locked(self) -> bool:
        """Return True if the account is currently locked."""
        if self.lock_until is None:
            return False
        return timezone.now() < self.lock_until

    def increment_failed_attempts(self, max_attempts: int, lockout_minutes: int) -> None:
        """Increment failed attempts and lock if threshold reached."""
        self.failed_attempts += 1
        if self.failed_attempts >= max_attempts:
            self.lock_until = timezone.now() + timezone.timedelta(
                minutes=lockout_minutes
            )
        self.save(update_fields=["failed_attempts", "lock_until"])

    def reset_failed_attempts(self) -> None:
        """Reset failed attempts after successful authentication."""
        self.failed_attempts = 0
        self.lock_until = None
        self.save(update_fields=["failed_attempts", "lock_until"])


class AdminRole(models.TextChoices):
    """Election administration roles as defined in the electoral board structure."""
    ELECTORAL_BOARD_HEAD = "electoral_board_head", "Electoral Board Head"
    ELECTORAL_BOARD_OPERATOR = "electoral_board_operator", "Electoral Board Operator"
    TALLY_WATCHER = "tally_watcher", "Tally Watcher"
    AUDITOR = "auditor", "Auditor"
    TECHNICAL_SUPPORT = "technical_support", "Technical Support"


class AdminProfile(models.Model):
    """
    Links a Django auth User to an election administration role.

    Admin authentication goes through Django's built-in auth (username + password),
    which is completely separate from student authentication (student_id + birthdate).
    Each admin must have exactly one role.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_profile",
    )
    role = models.CharField(
        max_length=30,
        choices=AdminRole.choices,
        db_index=True,
    )
    display_name = models.CharField(
        max_length=255,
        help_text="Human-readable name shown in audit logs and UI.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive admin profiles cannot authenticate.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]
        verbose_name = "Admin Profile"
        verbose_name_plural = "Admin Profiles"

    def __str__(self) -> str:
        return f"{self.display_name} ({self.get_role_display()})"

    @property
    def is_electoral_board_head(self) -> bool:
        return self.role == AdminRole.ELECTORAL_BOARD_HEAD

    @property
    def is_operator(self) -> bool:
        return self.role == AdminRole.ELECTORAL_BOARD_OPERATOR

    @property
    def is_read_only(self) -> bool:
        return self.role in (
            AdminRole.TALLY_WATCHER,
            AdminRole.AUDITOR,
            AdminRole.TECHNICAL_SUPPORT,
        )
