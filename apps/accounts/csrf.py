"""Safe CSRF failure responses for browser-facing API requests."""

import logging

from django.http import HttpResponseForbidden, JsonResponse

from apps.accounts.utils import get_ratelimit_client_ip, get_user_agent

logger = logging.getLogger("cems.security")

CSRF_CLIENT_ERROR = (
    "Security verification failed. Refresh the page and try again. "
    "If you opened CEMS in Messenger, open carigcems.com in Chrome or Safari."
)


def csrf_failure(request, reason=""):
    """Log the internal CSRF reason while returning a safe client response."""
    logger.warning(
        "CSRF verification failed: %s",
        reason or "unspecified reason",
        extra={
            "path": request.path,
            "ip_address": get_ratelimit_client_ip(None, request),
            "user_agent": get_user_agent(request),
        },
    )

    if request.path.startswith("/api/"):
        return JsonResponse(
            {"success": False, "error": CSRF_CLIENT_ERROR},
            status=403,
        )

    return HttpResponseForbidden(
        "Security verification failed. Refresh the page and try again."
    )
