"""
Shared utility functions for the accounts app.
"""


def get_client_ip(request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a trusted proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_user_agent(request) -> str:
    """Extract the User-Agent header from a request."""
    return request.META.get("HTTP_USER_AGENT", "")
