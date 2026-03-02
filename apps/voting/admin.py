"""Voting admin — read-only vote inspection."""
from django.contrib import admin

from apps.voting.models import Vote


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    """
    Vote records are immutable. Admin may inspect but NEVER edit or delete.
    """

    list_display = ("id", "position", "candidate", "timestamp")
    list_filter = ("position",)
    search_fields = ("hashed_student_id",)
    readonly_fields = (
        "id",
        "hashed_student_id",
        "candidate",
        "position",
        "timestamp",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False
