"""Voting admin — read-only ballot inspection."""
from django.contrib import admin

from apps.voting.models import Ballot, BallotSelection


class BallotSelectionInline(admin.TabularInline):
    """Read-only inline showing each selection within a ballot."""

    model = BallotSelection
    extra = 0
    fields = ("position", "candidate")
    readonly_fields = ("position", "candidate")

    def has_add_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False


@admin.register(Ballot)
class BallotAdmin(admin.ModelAdmin):
    """
    Ballot records are immutable.  Admin may inspect but NEVER edit or delete.
    """

    list_display = ("id", "election", "timestamp")
    list_filter = ("election",)
    search_fields = ("hashed_student_id",)
    readonly_fields = ("id", "election", "hashed_student_id", "timestamp")
    ordering = ("-timestamp",)
    inlines = [BallotSelectionInline]

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False


@admin.register(BallotSelection)
class BallotSelectionAdmin(admin.ModelAdmin):
    """
    Individual selections are also immutable.
    """

    list_display = ("ballot", "position", "candidate")
    list_filter = ("position__election", "position")
    search_fields = ("ballot__hashed_student_id", "candidate__full_name")
    readonly_fields = ("ballot", "position", "candidate")

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False
