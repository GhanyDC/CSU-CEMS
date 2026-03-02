"""
Production settings for CEMS.

Inherits from base.py. All security settings are kept at their
hardened defaults defined in base.py.
"""
from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Debug — MUST be False
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
# Security — production hardened (base.py already sets secure defaults)
# ---------------------------------------------------------------------------
# Additional production middleware
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Email — configure for production
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Logging — reduce noise in production
# ---------------------------------------------------------------------------
LOGGING["loggers"]["django"]["level"] = "WARNING"  # noqa: F405
