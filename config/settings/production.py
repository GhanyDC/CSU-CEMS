"""
Production settings for CEMS.

Inherits from base.py. All security settings are kept at their
hardened defaults defined in base.py.
"""
from decouple import Csv, config

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

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# ---------------------------------------------------------------------------
# Email — configure for production
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Logging — reduce noise in production
# ---------------------------------------------------------------------------
LOGGING["loggers"]["django"]["level"] = "WARNING"  # noqa: F405
