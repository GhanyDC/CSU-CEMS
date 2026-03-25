"""Elections admin — Election, Position, and Candidate management."""
from django.contrib import admin

from apps.elections.models import Candidate, Election, Position


class PositionInline(admin.TabularInline):
    """Inline positions within an Election change page."""

    model = Position
    extra = 1
    fields = ("title", "category", "max_selections", "order")
    ordering = ("order",)


class CandidateInline(admin.TabularInline):
    """Inline candidates within a Position change page."""

    model = Candidate
    extra = 1
    fields = ("full_name", "party", "college", "is_active")


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "start_time", "end_time", "created_at")
    list_filter = ("status",)
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-start_time",)
    inlines = [PositionInline]


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("title", "election", "category", "max_selections", "order")
    list_filter = ("category", "election")
    search_fields = ("title", "election__name")
    readonly_fields = ("id",)
    ordering = ("election", "order", "title")
    inlines = [CandidateInline]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "party", "college", "is_active", "created_at")
    list_filter = ("position__category", "is_active", "position__election")
    search_fields = ("full_name", "party", "college")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("position__order", "full_name")
