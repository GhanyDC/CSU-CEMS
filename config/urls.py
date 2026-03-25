"""
CEMS URL Configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns: list = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/elections/", include("apps.elections.urls", namespace="elections")),
    path("api/voting/", include("apps.voting.urls", namespace="voting")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
