"""
Test settings — uses SQLite for fast local pytest runs without Docker.

Inherits from local.py but overrides the database to SQLite.
"""
from .local import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Database — SQLite for unit testing only
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ---------------------------------------------------------------------------
# Performance — speed up password hashing in tests
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# Disable debug toolbar in tests
# ---------------------------------------------------------------------------
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405

# ---------------------------------------------------------------------------
# Rate limiting — disable in tests to avoid flaky test failures
# ---------------------------------------------------------------------------
RATELIMIT_ENABLE = False
