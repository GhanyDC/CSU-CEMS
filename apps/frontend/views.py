"""
Frontend views — serve HTML templates for the CEMS web interface.

All business logic is handled by the existing API endpoints.
These views only render templates; the templates use JavaScript
to interact with the REST API.
"""
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect


def login_page(request):
    """Render the login page. Redirect to dashboard if already logged in."""
    if request.session.get("authenticated_student_id"):
        return redirect("frontend:dashboard")
    # Ensure CSRF cookie is set for the login form
    get_token(request)
    return render(request, "frontend/login.html")


def dashboard_page(request):
    """Render the main dashboard."""
    if not request.session.get("authenticated_student_id"):
        return redirect("frontend:login")
    return render(request, "frontend/dashboard.html")


def ballot_page(request):
    """Render the ballot/voting page."""
    if not request.session.get("authenticated_student_id"):
        return redirect("frontend:login")
    return render(request, "frontend/ballot.html")


def results_page(request):
    """Render the results visualization page."""
    if not request.session.get("authenticated_student_id"):
        return redirect("frontend:login")
    return render(request, "frontend/results.html")


def admin_page(request):
    """Render the admin election management page."""
    if not request.session.get("authenticated_student_id"):
        return redirect("frontend:login")
    return render(request, "frontend/admin_panel.html")
