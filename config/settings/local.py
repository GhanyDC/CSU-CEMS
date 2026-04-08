"""
Local development settings for CEMS.

Inherits from base.py and relaxes security for local development.
"""
import copy
import importlib.util
import socket

from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# ---------------------------------------------------------------------------
# Security - relaxed for local dev
# ---------------------------------------------------------------------------
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False  # Allow JS to read CSRF token for API calls
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# ---------------------------------------------------------------------------
# Django Debug Toolbar
# ---------------------------------------------------------------------------
INTERNAL_IPS = ["127.0.0.1", "0.0.0.0"]

if importlib.util.find_spec("debug_toolbar") is not None:
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

try:
    _, _, ips = socket.gethostbyname_ex(socket.gethostname())
except OSError:
    ips = []

INTERNAL_IPS += [".".join(ip.split(".")[:-1] + ["1"]) for ip in ips if "." in ip]

# ---------------------------------------------------------------------------
# Email - console backend for local dev
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Logging - more verbose locally
# ---------------------------------------------------------------------------
LOGGING = copy.deepcopy(LOGGING)  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "DEBUG"

# Avoid writing log files inside the project tree in development.
# Django's autoreloader watches the repo and can reload on each request
# when request logging updates files under BASE_DIR/logs.
for handler_name in ("security_file", "login_file", "application_file"):
    LOGGING["handlers"].pop(handler_name, None)

for logger_name in ("django", "django.security", "cems.security", "cems.login", "cems.application"):
    if logger_name in LOGGING["loggers"]:
        LOGGING["loggers"][logger_name]["handlers"] = ["console"]

LOGGING["loggers"]["django.server"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}
