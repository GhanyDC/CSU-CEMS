"""
Base Django settings for CEMS project.

Security-hardened defaults. All environment-specific overrides
belong in local.py or production.py.
"""
import os
from pathlib import Path
from typing import List

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY: str = config("DJANGO_SECRET_KEY")
DEBUG: bool = False
ALLOWED_HOSTS: List[str] = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())
ROOT_URLCONF: str = "config.urls"
WSGI_APPLICATION: str = "config.wsgi.application"
DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS: List[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: List[str] = [
    "django_extensions",
]

LOCAL_APPS: List[str] = [
    "apps.accounts",
    "apps.elections",
    "apps.voting",
    "apps.audit",
    "apps.frontend",
]

INSTALLED_APPS: List[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE: List[str] = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.frontend.context_processors.bootstrap_context",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — PostgreSQL only in all environments
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="cems"),
        "USER": config("POSTGRES_USER", default="cems"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("CONN_MAX_AGE", default=60, cast=int),
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE: str = "en-us"
TIME_ZONE: str = "UTC"
USE_I18N: bool = True
USE_TZ: bool = True  # timezone-aware datetimes

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL: str = "/static/"
STATIC_ROOT: str = str(BASE_DIR / "staticfiles")
STATICFILES_DIRS: List[str] = [str(BASE_DIR / "static")]

# ---------------------------------------------------------------------------
# Media files (candidate photos, imports, etc.)
# ---------------------------------------------------------------------------
MEDIA_URL: str = "/media/"
MEDIA_ROOT: str = str(BASE_DIR / "media")

# Candidate photo constraints
CEMS_MAX_PHOTO_SIZE_MB: int = 2
CEMS_ALLOWED_PHOTO_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]

# ---------------------------------------------------------------------------
# Security — hardened defaults (overridden in local.py for dev)
# ---------------------------------------------------------------------------
# CSRF
CSRF_COOKIE_HTTPONLY: bool = True
CSRF_COOKIE_SECURE: bool = True

# Session
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SECURE: bool = True
SESSION_COOKIE_SAMESITE: str = "Lax"
SESSION_COOKIE_AGE: int = 3600  # 1 hour — appropriate for a voting application
SESSION_ENGINE: str = "django.contrib.sessions.backends.db"

# XSS / Clickjacking / MIME
SECURE_BROWSER_XSS_FILTER: bool = True
SECURE_CONTENT_TYPE_NOSNIFF: bool = True
X_FRAME_OPTIONS: str = "DENY"

# HSTS (production-only values; local.py disables)
SECURE_HSTS_SECONDS: int = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = True
SECURE_HSTS_PRELOAD: bool = True
SECURE_SSL_REDIRECT: bool = True

# ---------------------------------------------------------------------------
# CEMS – Application constants
# ---------------------------------------------------------------------------
CEMS_MAX_FAILED_ATTEMPTS: int = config("CEMS_MAX_FAILED_ATTEMPTS", default=5, cast=int)
CEMS_LOCKOUT_MINUTES: int = config("CEMS_LOCKOUT_MINUTES", default=30, cast=int)

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
RATELIMIT_ENABLE: bool = True

# ---------------------------------------------------------------------------
# Logging — imported from dedicated module to keep settings clean
# ---------------------------------------------------------------------------
LOG_DIR: Path = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module} {message}",
            "style": "{",
        },
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(module)s %(message)s",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "security_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "security.log"),
            "maxBytes": 1024 * 1024 * 10,  # 10 MB
            "backupCount": 10,
            "formatter": "json",
        },
        "login_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "login_attempts.log"),
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 10,
            "formatter": "json",
        },
        "application_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "application.log"),
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 10,
            "formatter": "json",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "application_file"],
            "level": "INFO",
            "propagate": True,
        },
        "django.security": {
            "handlers": ["console", "security_file"],
            "level": "INFO",
            "propagate": False,
        },
        "cems.security": {
            "handlers": ["console", "security_file"],
            "level": "INFO",
            "propagate": False,
        },
        "cems.login": {
            "handlers": ["console", "login_file"],
            "level": "INFO",
            "propagate": False,
        },
        "cems.application": {
            "handlers": ["console", "application_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
