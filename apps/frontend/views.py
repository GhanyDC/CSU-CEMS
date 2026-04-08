"""
Frontend views — serve HTML templates for the CEMS web interface.

All business logic is handled by the existing API endpoints.
These views only render templates; the templates use JavaScript
to interact with the REST API.
"""
from typing import Optional

from django.middleware.csrf import get_token
from django.shortcuts import render, redirect

from apps.accounts.models import AdminProfile, Student


def _get_authenticated_student(request) -> Optional[Student]:
    """Return the authenticated student from the session, if present and valid."""
    student_pk = request.session.get("authenticated_student_id")
    if not student_pk:
        return None

    try:
        return Student.objects.get(pk=student_pk)
    except Student.DoesNotExist:
        request.session.flush()
        return None


def _get_admin_profile(request) -> Optional[AdminProfile]:
    """Return the AdminProfile for a Django-auth-authenticated admin, if valid."""
    user = request.user
    if not user.is_authenticated:
        return None
    try:
        return AdminProfile.objects.get(user=user, is_active=True)
    except AdminProfile.DoesNotExist:
        return None


def _render_authenticated_page(request, template_name: str):
    """Render a protected page with server-bootstrapped user context."""
    student = _get_authenticated_student(request)
    if student is None:
        return redirect("frontend:login")

    return render(
        request,
        template_name,
        {
            "bootstrap_user": {
                "student_id": student.student_id,
                "full_name": student.full_name,
                "is_admin": student.is_admin,
            }
        },
    )


def login_page(request):
    """Render the login page. Redirect to dashboard if already logged in."""
    if _get_authenticated_student(request):
        return redirect("frontend:dashboard")
    # Ensure CSRF cookie is set for the login form
    get_token(request)
    return render(request, "frontend/login.html")


def dashboard_page(request):
    """Render the main dashboard."""
    return _render_authenticated_page(request, "frontend/dashboard.html")


def ballot_page(request):
    """Render the ballot/voting page."""
    return _render_authenticated_page(request, "frontend/ballot.html")


def results_page(request):
    """Render the results visualization page."""
    return _render_authenticated_page(request, "frontend/results.html")


def admin_login_page(request):
    """Render the admin login page. Redirect to admin panel if already logged in."""
    profile = _get_admin_profile(request)
    if profile is not None:
        return redirect("frontend:admin-panel")
    get_token(request)
    return render(request, "frontend/admin_login.html")


def admin_page(request):
    """Render the admin election management page (requires admin auth)."""
    profile = _get_admin_profile(request)
    if profile is None:
        return redirect("frontend:admin-login")

    context = {
        "bootstrap_admin": {
            "username": request.user.username,
            "display_name": profile.display_name,
            "role": profile.role,
            "role_display": profile.get_role_display(),
            "is_eb_head": profile.is_electoral_board_head,
            "is_operator": profile.is_operator,
            "is_read_only": profile.is_read_only,
        }
    }
    return render(request, "frontend/admin_panel.html", context)
