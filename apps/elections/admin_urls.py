"""
Admin election setup URL routing.
"""
from django.urls import path

from apps.elections import admin_views, export_views

app_name = "admin_elections"

urlpatterns = [
    # Election list and detail
    path("list/", admin_views.list_elections, name="list"),
    path("<uuid:election_id>/", admin_views.election_detail, name="detail"),

    # Election creation
    path("create-campus/", admin_views.create_campus_election, name="create-campus"),
    path("create-college/", admin_views.create_college_elections, name="create-college"),

    # Election management
    path("<uuid:election_id>/delete/", admin_views.delete_election, name="delete"),
    path("<uuid:election_id>/update/", admin_views.update_election_settings, name="update"),
    path("<uuid:election_id>/banner/", admin_views.upload_election_banner, name="upload-banner"),

    # Position management (EB Head only)
    path("<uuid:election_id>/positions/create/", admin_views.create_position, name="position-create"),
    path("<uuid:election_id>/positions/<uuid:position_id>/update/", admin_views.update_position, name="position-update"),
    path("<uuid:election_id>/positions/<uuid:position_id>/delete/", admin_views.delete_position, name="position-delete"),
    path("<uuid:election_id>/positions/reorder/", admin_views.reorder_positions, name="position-reorder"),

    # Candidate management
    path("<uuid:election_id>/candidates/add/", admin_views.add_candidate, name="add-candidate"),
    path(
        "<uuid:election_id>/candidates/<uuid:candidate_id>/update/",
        admin_views.update_candidate,
        name="update-candidate",
    ),
    path(
        "<uuid:election_id>/candidates/<uuid:candidate_id>/delete/",
        admin_views.delete_candidate,
        name="delete-candidate",
    ),
    path(
        "<uuid:election_id>/candidates/<uuid:candidate_id>/photo/",
        admin_views.upload_candidate_photo,
        name="upload-candidate-photo",
    ),

    # Voter roll management
    path("<uuid:election_id>/voter-roll/import/", admin_views.import_voter_roll, name="voter-roll-import"),
    path("<uuid:election_id>/voter-roll/summary/", admin_views.voter_roll_summary, name="voter-roll-summary"),
    path("<uuid:election_id>/voter-roll/generate/", admin_views.generate_voter_roll, name="voter-roll-generate"),
    path("<uuid:election_id>/voter-roll/finalize/", admin_views.finalize_voter_roll, name="voter-roll-finalize"),

    # Hybrid canvass
    path("<uuid:election_id>/hybrid/summary/", admin_views.hybrid_summary, name="hybrid-summary"),
    path("<uuid:election_id>/hybrid/roster/import/", admin_views.import_hybrid_roster, name="hybrid-roster-import"),
    path("<uuid:election_id>/hybrid/tally/template/", admin_views.download_hybrid_tally_template, name="hybrid-tally-template"),
    path("<uuid:election_id>/hybrid/tally/import/", admin_views.import_hybrid_tally, name="hybrid-tally-import"),

    # Registrar batch management
    path("registrar-batches/", admin_views.list_registrar_batches, name="registrar-batches"),
    path("registrar-batches/create/", admin_views.create_registrar_batch, name="registrar-batch-create"),
    path("registrar-batches/<uuid:batch_id>/import/", admin_views.import_registrar_batch, name="registrar-batch-import"),
    path("registrar-batches/<uuid:batch_id>/delete/", admin_views.delete_registrar_batch, name="registrar-batch-delete"),
    path("<uuid:election_id>/registrar-batch/assign/", admin_views.assign_registrar_batch, name="registrar-batch-assign"),

    # School-year roster and web registration
    path("school-years/", admin_views.list_school_years, name="school-years"),
    path("school-years/create/", admin_views.create_school_year, name="school-year-create"),
    path("school-years/<uuid:school_year_id>/activate/", admin_views.activate_school_year, name="school-year-activate"),
    path("school-years/<uuid:school_year_id>/archive/", admin_views.archive_school_year, name="school-year-archive"),
    path("school-years/<uuid:school_year_id>/enrollments/", admin_views.list_enrollments, name="school-year-enrollments"),
    path("school-years/<uuid:school_year_id>/enrollments/create/", admin_views.create_enrollment, name="enrollment-create"),
    path("enrollments/<uuid:enrollment_id>/update/", admin_views.update_enrollment, name="enrollment-update"),
    path("enrollments/<uuid:enrollment_id>/deactivate/", admin_views.deactivate_enrollment, name="enrollment-deactivate"),
    path("<uuid:election_id>/registration/settings/", admin_views.update_registration_settings, name="registration-settings"),
    path("<uuid:election_id>/registration/summary/", admin_views.registration_summary, name="registration-summary"),

    # Readiness check
    path("<uuid:election_id>/readiness/", admin_views.readiness_check, name="readiness"),

    # College management
    path("colleges/", admin_views.list_colleges, name="colleges"),
    path("colleges/create/", admin_views.create_college, name="college-create"),
    path("colleges/<uuid:college_id>/update/", admin_views.update_college, name="college-update"),
    path("colleges/<uuid:college_id>/delete/", admin_views.delete_college, name="college-delete"),

    # Export endpoints
    path("<uuid:election_id>/export/turnout/csv/", export_views.export_turnout_csv, name="export-turnout-csv"),
    path("<uuid:election_id>/export/turnout/text/", export_views.export_turnout_text, name="export-turnout-text"),
    path("<uuid:election_id>/export/tally/csv/", export_views.export_tally_csv, name="export-tally-csv"),
    path("<uuid:election_id>/export/participation/csv/", export_views.export_participation_csv, name="export-participation-csv"),
    path("<uuid:election_id>/export/ballot-audit/csv/", export_views.export_ballot_audit_csv, name="export-ballot-audit-csv"),

    # Post-audit college-rep endpoints
    path("<uuid:election_id>/audit/college-rep/", export_views.college_rep_audit_json, name="college-rep-audit-json"),
    path("<uuid:election_id>/export/college-rep-audit/csv/", export_views.export_college_rep_audit_csv, name="export-college-rep-audit-csv"),
]
