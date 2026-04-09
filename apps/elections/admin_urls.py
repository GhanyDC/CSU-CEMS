"""
Admin election setup URL routing.
"""
from django.urls import path

from apps.elections import admin_views

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
    path("<uuid:election_id>/banner/", admin_views.upload_election_banner, name="upload-banner"),

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

    # Registrar batch management
    path("registrar-batches/", admin_views.list_registrar_batches, name="registrar-batches"),
    path("registrar-batches/create/", admin_views.create_registrar_batch, name="registrar-batch-create"),
    path("registrar-batches/<uuid:batch_id>/import/", admin_views.import_registrar_batch, name="registrar-batch-import"),
    path("registrar-batches/<uuid:batch_id>/delete/", admin_views.delete_registrar_batch, name="registrar-batch-delete"),
    path("<uuid:election_id>/registrar-batch/assign/", admin_views.assign_registrar_batch, name="registrar-batch-assign"),

    # Readiness check
    path("<uuid:election_id>/readiness/", admin_views.readiness_check, name="readiness"),

    # College management
    path("colleges/", admin_views.list_colleges, name="colleges"),
    path("colleges/create/", admin_views.create_college, name="college-create"),
    path("colleges/<uuid:college_id>/update/", admin_views.update_college, name="college-update"),
    path("colleges/<uuid:college_id>/delete/", admin_views.delete_college, name="college-delete"),
]
