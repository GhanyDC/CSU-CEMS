"""Accounts admin — Student and AdminProfile management."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from apps.accounts.models import AdminProfile, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "student_id",
        "full_name",
        "college",
        "course",
        "year",
        "is_admin",
        "failed_attempts",
        "is_locked",
        "created_at",
    )
    list_filter = ("is_admin", "college", "course", "year")
    search_fields = ("student_id", "full_name")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("student_id",)

    def is_locked(self, obj: Student) -> bool:
        return obj.is_locked

    is_locked.boolean = True  # type: ignore[attr-defined]
    is_locked.short_description = "Locked"  # type: ignore[attr-defined]


class AdminProfileInline(admin.StackedInline):
    model = AdminProfile
    can_delete = False
    verbose_name_plural = "Admin Profile"
    readonly_fields = ("id", "created_at", "updated_at")


class UserWithAdminProfile(BaseUserAdmin):
    inlines = (AdminProfileInline,)
    list_display = BaseUserAdmin.list_display + ("get_admin_role",)

    def get_admin_role(self, obj):
        try:
            return obj.admin_profile.get_role_display()
        except AdminProfile.DoesNotExist:
            return "—"

    get_admin_role.short_description = "Admin Role"


# Re-register User with admin profile inline
admin.site.unregister(User)
admin.site.register(User, UserWithAdminProfile)


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "role", "user", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("display_name", "user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("display_name",)
