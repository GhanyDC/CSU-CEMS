"""
Audit service — helper to record security events.
"""
import logging
from typing import Optional

from apps.audit.models import AuditLog

security_logger = logging.getLogger("cems.security")
login_logger = logging.getLogger("cems.login")


class AuditService:
    """Centralised audit event recording."""

    @staticmethod
    def log_event(
        *,
        student_id_attempted: str,
        event_type: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: str = "",
        details: str = "",
    ) -> AuditLog:
        """
        Create an immutable audit record and emit a structured log.
        """
        record: AuditLog = AuditLog.objects.create(
            student_id_attempted=student_id_attempted,
            event_type=event_type,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

        log_data = {
            "audit_id": str(record.id),
            "student_id_attempted": student_id_attempted,
            "event_type": event_type,
            "success": success,
            "ip_address": ip_address,
        }

        if event_type == AuditLog.EventType.LOGIN_ATTEMPT:
            if success:
                login_logger.info("Login success", extra=log_data)
            else:
                login_logger.warning("Login failed", extra=log_data)
        elif event_type == AuditLog.EventType.SUSPICIOUS_ACTIVITY:
            security_logger.warning("Suspicious activity", extra=log_data)
        else:
            security_logger.info("Security event", extra=log_data)

        return record
