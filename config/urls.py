"""
CEMS URL Configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.elections.views import close_election, publish_results, start_election

urlpatterns: list = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/elections/", include("apps.elections.urls", namespace="elections")),
    path("api/voting/", include("apps.voting.urls", namespace="voting")),
    # Admin lifecycle endpoints
    path("api/admin/elections/start/", start_election, name="election-start"),
    path("api/admin/elections/close/", close_election, name="election-close"),
    path("api/admin/elections/publish/", publish_results, name="election-publish"),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
