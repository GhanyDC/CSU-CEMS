"""
Authentication decorators for CEMS views.

Two separate auth systems:
  - Student: session-based via ``authenticated_student_id``
  - Admin:   Django auth via ``request.user`` + AdminProfile
"""
import functools

from django.http import JsonResponse

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.accounts.utils import get_client_ip, get_user_agent
from apps.audit.models import AuditLog
from apps.audit.services import AuditService


def login_required_student(view_func):
    """
    Decorator that ensures the request has a valid authenticated student session.

    Attaches ``request.student`` on success.
    Returns 401 JSON if session is missing or student no longer exists.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        student_pk = request.session.get("authenticated_student_id")
        if not student_pk:
            return JsonResponse(
                {"success": False, "error": "Authentication required."},
                status=401,
            )
        try:
            request.student = Student.objects.get(pk=student_pk)
        except Student.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Authentication required."},
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """
    Legacy decorator — kept for backward compatibility.
    Checks the student ``is_admin`` flag. New admin views should use
    ``admin_login_required`` instead.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, "student", None) or not request.student.is_admin:
            return JsonResponse(
                {"success": False, "error": "Admin privileges required."},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# New admin auth decorators (Bundle 01)
# ---------------------------------------------------------------------------

def admin_login_required(view_func):
    """
    Ensure the request comes from an authenticated admin user
    (Django auth User with an active AdminProfile).

    Attaches ``request.admin_profile`` on success.
    Returns 401 if not authenticated or no active profile exists.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse(
                {"success": False, "error": "Admin authentication required."},
                status=401,
            )

        try:
            profile = AdminProfile.objects.select_related("user").get(
                user=user, is_active=True
            )
        except AdminProfile.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Admin authentication required."},
                status=401,
            )

        request.admin_profile = profile
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    """
    Restrict access to admins whose role is in ``allowed_roles``.

    Must be applied AFTER ``admin_login_required``.
    Logs a PERMISSION_DENIED audit event when access is refused.

    Usage::

        @admin_login_required
        @role_required(AdminRole.ELECTORAL_BOARD_HEAD, AdminRole.ELECTORAL_BOARD_OPERATOR)
        def my_view(request): ...
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            profile = getattr(request, "admin_profile", None)
            if profile is None or profile.role not in allowed_roles:
                # Audit the denied attempt
                actor = "unknown"
                if profile:
                    actor = profile.user.username
                elif hasattr(request, "user") and request.user.is_authenticated:
                    actor = request.user.username

                AuditService.log_event(
                    student_id_attempted=actor,
                    event_type=AuditLog.EventType.ADMIN_PERMISSION_DENIED,
                    success=False,
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                    details=(
                        f"Role '{getattr(profile, 'role', 'none')}' "
                        f"denied access to {view_func.__name__}. "
                        f"Required: {', '.join(allowed_roles)}."
                    ),
                )
                return JsonResponse(
                    {"success": False, "error": "You do not have permission for this action."},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def electoral_board_head_required(view_func):
    """
    Convenience decorator: ``admin_login_required`` + Electoral Board Head role check.

    Use for actions only the VP / Electoral Board Head may perform:
    finalize voter rolls, start/close/publish elections.
    """

    @functools.wraps(view_func)
    @admin_login_required
    @role_required(AdminRole.ELECTORAL_BOARD_HEAD)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper
