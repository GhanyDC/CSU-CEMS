"""Elections admin — Candidate management."""
from django.contrib import admin

from apps.elections.models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "party", "is_active", "created_at")
    list_filter = ("position", "is_active")
    search_fields = ("full_name", "party")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("position", "full_name")
