from django.urls import path

from . import views

app_name = "accounts"

urlpatterns: list = [
    path("login/", views.student_login, name="login"),
    path("logout/", views.student_logout, name="logout"),
]
