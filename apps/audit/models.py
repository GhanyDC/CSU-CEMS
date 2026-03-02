"""
Audit models — immutable security event log.
"""
import uuid

from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of security-relevant events.

    Every login attempt, vote cast, and suspicious activity
    is recorded in this table. Records must NEVER be deleted
    or modified in production.
    """

    class EventType(models.TextChoices):
        LOGIN_ATTEMPT = "login_attempt", "Login Attempt"
        VOTE_CAST = "vote_cast", "Vote Cast"
        SUSPICIOUS_ACTIVITY = "suspicious_activity", "Suspicious Activity"

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    student_id_attempted: models.CharField = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Student ID that was used in the attempt.",
    )
    ip_address: models.GenericIPAddressField = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    user_agent: models.TextField = models.TextField(
        blank=True,
        default="",
    )
    success: models.BooleanField = models.BooleanField(default=False)
    event_type: models.CharField = models.CharField(
        max_length=30,
        choices=EventType.choices,
        db_index=True,
    )
    details: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Additional context about the event.",
    )
    timestamp: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self) -> str:
        return (
            f"[{self.event_type}] {self.student_id_attempted} "
            f"@ {self.timestamp:%Y-%m-%d %H:%M:%S}"
        )
