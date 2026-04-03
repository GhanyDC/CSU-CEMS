from django.urls import path

from apps.frontend import views

app_name = "frontend"

urlpatterns = [
    path("", views.login_page, name="login"),
    path("dashboard/", views.dashboard_page, name="dashboard"),
    path("ballot/", views.ballot_page, name="ballot"),
    path("results/", views.results_page, name="results"),
    path("admin-panel/", views.admin_page, name="admin-panel"),
]
