"""
Tests for audit logging.

Covers:
- Audit records created on login attempts
- Audit records for vote events
- Fields are populated correctly
"""
import pytest
from datetime import date

from apps.audit.models import AuditLog
from apps.audit.services import AuditService


@pytest.mark.django_db
class TestAuditLogging:
    """Test suite for audit log creation."""

    def test_create_login_attempt_record(self) -> None:
        """AuditService creates a login_attempt record."""
        record = AuditService.log_event(
            student_id_attempted="AUD001",
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            details="Test failure",
        )
        assert record.student_id_attempted == "AUD001"
        assert record.event_type == AuditLog.EventType.LOGIN_ATTEMPT
        assert record.success is False
        assert record.ip_address == "192.168.1.1"
        assert record.user_agent == "TestAgent/1.0"

    def test_create_vote_cast_record(self) -> None:
        """AuditService creates a vote_cast record."""
        record = AuditService.log_event(
            student_id_attempted="AUD002",
            event_type=AuditLog.EventType.VOTE_CAST,
            success=True,
            ip_address="10.0.0.1",
        )
        assert record.event_type == AuditLog.EventType.VOTE_CAST
        assert record.success is True

    def test_create_suspicious_activity_record(self) -> None:
        """AuditService creates a suspicious_activity record."""
        record = AuditService.log_event(
            student_id_attempted="AUD003",
            event_type=AuditLog.EventType.SUSPICIOUS_ACTIVITY,
            success=False,
            ip_address="172.16.0.1",
            details="Multiple rapid login attempts detected",
        )
        assert record.event_type == AuditLog.EventType.SUSPICIOUS_ACTIVITY
        assert "rapid" in record.details

    def test_audit_record_has_uuid_pk(self) -> None:
        """Audit records use UUID primary keys."""
        record = AuditService.log_event(
            student_id_attempted="AUD004",
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=True,
        )
        assert record.id is not None
        assert len(str(record.id)) == 36  # UUID format

    def test_audit_timestamp_is_set(self) -> None:
        """Audit records have a non-null timestamp."""
        record = AuditService.log_event(
            student_id_attempted="AUD005",
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=True,
        )
        assert record.timestamp is not None

    def test_multiple_audit_records(self) -> None:
        """Multiple events create separate records."""
        for i in range(5):
            AuditService.log_event(
                student_id_attempted=f"AUD{i:03d}",
                event_type=AuditLog.EventType.LOGIN_ATTEMPT,
                success=(i % 2 == 0),
            )
        assert AuditLog.objects.count() == 5
