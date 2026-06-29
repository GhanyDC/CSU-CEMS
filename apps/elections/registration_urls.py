"""URL routes for student web voter registration."""

from django.urls import path

from apps.elections import registration_views

app_name = "registration"

urlpatterns = [
    path("available/", registration_views.available_registrations, name="available"),
    path(
        "elections/<uuid:election_id>/status/",
        registration_views.registration_status,
        name="status",
    ),
    path(
        "elections/<uuid:election_id>/register/",
        registration_views.register_for_election,
        name="register",
    ),
]
