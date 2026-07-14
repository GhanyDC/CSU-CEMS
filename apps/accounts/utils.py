"""
Shared utility functions for the accounts app.
"""

from django.conf import settings


def get_ratelimit_client_ip(group, request) -> str:
    """Return the client IP set by the trusted reverse proxy.

    Nginx overwrites ``X-Real-IP`` before proxying to Django, so it is safe to
    use for rate-limit buckets.  Deliberately do not use X-Forwarded-For here:
    its left-most value can be supplied by an untrusted client.
    """
    del group  # Required by django-ratelimit's callable key signature.
    real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
    if real_ip:
        return real_ip
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_student_login_rate(group, request) -> str:
    """Return the configurable NAT-friendly student login rate."""
    del group, request
    return settings.CEMS_STUDENT_LOGIN_RATE


def get_admin_login_rate(group, request) -> str:
    """Return the stricter configurable admin login rate."""
    del group, request
    return settings.CEMS_ADMIN_LOGIN_RATE


def get_client_ip(request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a trusted proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_user_agent(request) -> str:
    """Extract the User-Agent header from a request."""
    return request.META.get("HTTP_USER_AGENT", "")
