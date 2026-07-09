"""Elections admin — election setup, voter roll, and hybrid canvass models."""
from django.contrib import admin

from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    EnrollmentRecord,
    HybridImportBatch,
    OnsiteParticipation,
    OnsiteTally,
    Position,
    RegistrarRecord,
    SchoolYear,
    VoterRegistration,
    VerificationRecord,
)


class PositionInline(admin.TabularInline):
    """Inline positions within an Election change page."""

    model = Position
    extra = 1
    fields = ("title", "category", "scope_college", "max_selections", "order")
    ordering = ("order",)


class CandidateInline(admin.TabularInline):
    """Inline candidates within a Position change page."""

    model = Candidate
    extra = 1
    fields = ("full_name", "party", "college", "is_active")


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "election_type", "voting_mode", "college", "status", "school_year", "registration_enabled", "start_time", "end_time", "voter_roll_finalized_at", "created_at")
    list_filter = ("status", "election_type", "voting_mode", "registration_enabled", "school_year")
    search_fields = ("name", "college")
    readonly_fields = ("id", "created_at", "updated_at", "voter_roll_finalized_at", "voter_roll_finalized_by")
    ordering = ("-start_time",)
    inlines = [PositionInline]


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("title", "election", "category", "scope_college", "max_selections", "order")
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


@admin.register(RegistrarRecord)
class RegistrarRecordAdmin(admin.ModelAdmin):
    list_display = ("student_identifier", "full_name", "batch", "college", "course", "year_level", "status")
    list_filter = ("batch", "status", "college")
    search_fields = ("student_identifier", "full_name", "student__student_id", "batch__name")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("batch", "student_identifier")


@admin.register(SchoolYear)
class SchoolYearAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "academic_year")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(EnrollmentRecord)
class EnrollmentRecordAdmin(admin.ModelAdmin):
    list_display = ("student_identifier", "full_name", "school_year", "college", "course", "year_level", "status")
    list_filter = ("school_year", "status", "college")
    search_fields = ("student_identifier", "full_name", "student__student_id")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("school_year", "student_identifier")


@admin.register(VoterRegistration)
class VoterRegistrationAdmin(admin.ModelAdmin):
    list_display = ("student", "election", "status", "source", "college_snapshot", "registrar_record", "requested_at", "decided_at")
    list_filter = ("status", "source", "election", "college_snapshot", "registrar_record__batch")
    search_fields = ("student__student_id", "student__full_name", "election__name")
    readonly_fields = ("id", "requested_at")
    ordering = ("-requested_at",)


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
