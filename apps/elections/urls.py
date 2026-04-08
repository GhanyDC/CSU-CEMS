from django.urls import path

from apps.elections import views

app_name = "elections"

urlpatterns: list = [
    # Student-facing election endpoints
    path("mine/", views.my_elections, name="mine"),
    path("<uuid:election_id>/ballot/", views.election_ballot, name="ballot"),
    path("current/", views.current_election, name="current"),
    path("status/", views.voting_status, name="status"),
    path("results/", views.election_results, name="results"),
    path("results/<uuid:election_id>/", views.election_results, name="results-detail"),
]
