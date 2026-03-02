"""Audit admin — read-only audit log inspection."""
from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Audit logs are immutable. Admin may inspect but NEVER edit or delete.
    """

    list_display = (
        "timestamp",
        "event_type",
        "student_id_attempted",
        "success",
        "ip_address",
    )
    list_filter = ("event_type", "success")
    search_fields = ("student_id_attempted", "ip_address")
    readonly_fields = (
        "id",
        "student_id_attempted",
        "ip_address",
        "user_agent",
        "success",
        "event_type",
        "details",
        "timestamp",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False
