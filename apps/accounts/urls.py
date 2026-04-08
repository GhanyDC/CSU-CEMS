from django.urls import path

from . import views

app_name = "accounts"

urlpatterns: list = [
    # Student authentication
    path("login/", views.student_login, name="login"),
    path("logout/", views.student_logout, name="logout"),
]

# Admin authentication — mounted separately at /api/admin/auth/ in config/urls.py
admin_auth_urlpatterns: list = [
    path("login/", views.admin_login, name="admin-login"),
    path("logout/", views.admin_logout, name="admin-logout"),
]
