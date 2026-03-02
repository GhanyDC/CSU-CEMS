"""Accounts admin — Student management."""
from django.contrib import admin

from apps.accounts.models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "student_id",
        "full_name",
        "course",
        "year",
        "has_voted",
        "failed_attempts",
        "is_locked",
        "created_at",
    )
    list_filter = ("has_voted", "course", "year")
    search_fields = ("student_id", "full_name")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("student_id",)

    def is_locked(self, obj: Student) -> bool:
        return obj.is_locked

    is_locked.boolean = True  # type: ignore[attr-defined]
    is_locked.short_description = "Locked"  # type: ignore[attr-defined]
