"""
Authentication decorators for CEMS views.
"""
import functools

from django.http import JsonResponse

from apps.accounts.models import Student


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
    Decorator that ensures the authenticated student has admin privileges.

    Must be applied AFTER ``login_required_student``.
    Returns 403 JSON if the student is not an admin.
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
