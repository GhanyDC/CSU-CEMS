"""Elections admin — election setup, voter roll, and hybrid canvass models."""
from django.contrib import admin

from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    HybridImportBatch,
    OnsiteParticipation,
    OnsiteTally,
    Position,
    VerificationRecord,
)


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
    list_display = ("name", "election_type", "voting_mode", "college", "status", "start_time", "end_time", "voter_roll_finalized_at", "created_at")
    list_filter = ("status", "election_type", "voting_mode")
    search_fields = ("name", "college")
    readonly_fields = ("id", "created_at", "updated_at", "voter_roll_finalized_at", "voter_roll_finalized_by")
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


@admin.register(EligibleVoter)
class EligibleVoterAdmin(admin.ModelAdmin):
    list_display = ("student", "election", "college_snapshot", "created_at")
    list_filter = ("election", "college_snapshot")
    search_fields = ("student__student_id", "student__full_name", "college_snapshot")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)


@admin.register(VerificationRecord)
class VerificationRecordAdmin(admin.ModelAdmin):
    list_display = ("student_id_input", "full_name_input", "election", "status", "matched_student", "imported_at")
    list_filter = ("status", "election")
    search_fields = ("student_id_input", "full_name_input")
    readonly_fields = ("id", "imported_at")
    ordering = ("-imported_at",)


@admin.register(HybridImportBatch)
class HybridImportBatchAdmin(admin.ModelAdmin):
    list_display = ("election", "batch_type", "status", "source_filename", "imported_by", "created_at")
    list_filter = ("batch_type", "status")
    search_fields = ("election__name", "source_filename", "imported_by")
    readonly_fields = ("id", "created_at", "updated_at", "activated_at")


@admin.register(OnsiteParticipation)
class OnsiteParticipationAdmin(admin.ModelAdmin):
    list_display = ("student", "batch", "created_at")
    list_filter = ("batch__election",)
    search_fields = ("student__student_id", "student__full_name", "batch__election__name")
    readonly_fields = ("id", "created_at")


@admin.register(OnsiteTally)
class OnsiteTallyAdmin(admin.ModelAdmin):
    list_display = ("candidate", "position", "onsite_votes", "batch", "created_at")
    list_filter = ("batch__election", "position")
    search_fields = ("candidate__full_name", "position__title", "batch__election__name")
    readonly_fields = ("id", "created_at")
