"""
CEMS URL Configuration.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns: list = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/elections/", include("apps.elections.urls", namespace="elections")),
    path("api/voting/", include("apps.voting.urls", namespace="voting")),
]
