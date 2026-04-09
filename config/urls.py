"""
CEMS URL Configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts.urls import admin_auth_urlpatterns
from apps.elections.views import (
    close_election, election_tally_review, election_turnout,
    publish_results, start_election,
)

urlpatterns: list = [
    path("admin/", admin.site.urls),
    # API endpoints — student auth
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/elections/", include("apps.elections.urls", namespace="elections")),
    path("api/voting/", include("apps.voting.urls", namespace="voting")),
    # API endpoints — admin auth
    path("api/admin/auth/", include((admin_auth_urlpatterns, "admin_auth"))),
    # Admin lifecycle endpoints (Electoral Board Head only)
    path("api/admin/elections/start/", start_election, name="election-start"),
    path("api/admin/elections/close/", close_election, name="election-close"),
    path("api/admin/elections/publish/", publish_results, name="election-publish"),
    # Admin monitoring endpoints
    path("api/admin/elections/<uuid:election_id>/turnout/", election_turnout, name="election-turnout"),
    path("api/admin/elections/<uuid:election_id>/tally/", election_tally_review, name="election-tally"),
    # Admin election setup endpoints (Operator + EB Head)
    path("api/admin/elections/setup/", include("apps.elections.admin_urls", namespace="admin_elections")),
    # Frontend UI
    path("", include("apps.frontend.urls", namespace="frontend")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
