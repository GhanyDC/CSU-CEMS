from django.urls import path

from apps.voting import views

app_name = "voting"

urlpatterns: list = [
    path("cast/", views.cast_ballot, name="cast"),
]
