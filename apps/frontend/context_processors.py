"""
Shared template context for frontend pages.
"""


def bootstrap_context(request):
    """Provide safe defaults for base template bootstrap payloads."""
    return {
        "bootstrap_user": None,
        "bootstrap_admin": None,
    }
