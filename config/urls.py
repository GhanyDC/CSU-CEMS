"""
CEMS URL Configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts.urls import admin_auth_urlpatterns
from apps.elections.views import close_election, publish_results, start_election

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
    # Frontend UI
    path("", include("apps.frontend.urls", namespace="frontend")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
