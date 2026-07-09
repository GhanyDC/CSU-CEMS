"""
Accounts views — authentication endpoints for students and admins.

Two completely separate authentication flows:
  - Student: student_id + date_of_birth → custom session
  - Admin:   username + password → Django auth session

Security measures:
- Rate limiting by IP (django-ratelimit)
- Account lock after N failed attempts (student)
- Generic error messages (never reveal whether accounts exist)
- Full audit logging of every attempt
"""
import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.accounts.models import AdminProfile, Student
from apps.accounts.utils import get_client_ip, get_user_agent
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.models import RegistrarImportBatch, RegistrarRecord

logger = logging.getLogger("cems.login")

# Generic message — NEVER reveal whether a student_id exists
GENERIC_AUTH_ERROR: str = "Invalid credentials. Please try again."
ACCOUNT_LOCKED_ERROR: str = "Account is temporarily locked. Please try again later."


@require_POST
@csrf_protect
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def student_login(request: Any) -> JsonResponse:
    """
    Authenticate a student by student_id + date_of_birth.

    POST body (JSON or form-encoded):
        student_id: str
        date_of_birth: str (YYYY-MM-DD)

    Returns JSON with:
        - 200: {"success": true, "student_id": "…"}
        - 400: missing fields
        - 401: invalid credentials / locked
        - 429: rate limited (handled by decorator)
    """
    import json

    ip_address: str = get_client_ip(request)
    user_agent: str = get_user_agent(request)

    # --- Parse input ---
    try:
        if request.content_type == "application/json":
            body: Dict[str, Any] = json.loads(request.body)
        else:
            body = request.POST.dict()
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"success": False, "error": "Invalid request body."}, status=400)

    student_id: Optional[str] = body.get("student_id")
    dob_raw: Optional[str] = body.get("date_of_birth")

    if not student_id or not dob_raw:
        return JsonResponse(
            {"success": False, "error": "student_id and date_of_birth are required."},
            status=400,
        )

    # Parse date_of_birth
    try:
        dob: date = date.fromisoformat(dob_raw)
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error": "date_of_birth must be in YYYY-MM-DD format."},
            status=400,
        )

    # --- Lookup student ---
    try:
        student: Student = Student.objects.get(student_id=student_id)
    except Student.DoesNotExist:
        # Log the attempt but return a generic error
        AuditService.log_event(
            student_id_attempted=student_id,
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details="Student ID not found.",
        )
        return JsonResponse(
            {"success": False, "error": GENERIC_AUTH_ERROR},
            status=401,
        )

    # --- Check account lock ---
    if student.is_locked:
        AuditService.log_event(
            student_id_attempted=student_id,
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details="Account is locked.",
        )
        return JsonResponse(
            {"success": False, "error": ACCOUNT_LOCKED_ERROR},
            status=401,
        )

    # --- Verify date of birth ---
    if student.date_of_birth != dob:
        student.increment_failed_attempts(
            max_attempts=settings.CEMS_MAX_FAILED_ATTEMPTS,
            lockout_minutes=settings.CEMS_LOCKOUT_MINUTES,
        )
        AuditService.log_event(
            student_id_attempted=student_id,
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details=f"Incorrect date_of_birth. Attempt #{student.failed_attempts}.",
        )
        return JsonResponse(
            {"success": False, "error": GENERIC_AUTH_ERROR},
            status=401,
        )

    # --- Success ---
    has_active_registrar_membership = RegistrarRecord.objects.filter(
        student=student,
        status=RegistrarRecord.Status.ACTIVE,
        batch__status=RegistrarImportBatch.Status.ACTIVE,
    ).exists()
    if not has_active_registrar_membership:
        AuditService.log_event(
            student_id_attempted=student_id,
            event_type=AuditLog.EventType.LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details="No active registrar batch membership.",
        )
        return JsonResponse(
            {"success": False, "error": GENERIC_AUTH_ERROR},
            status=401,
        )

    student.reset_failed_attempts()

    AuditService.log_event(
        student_id_attempted=student_id,
        event_type=AuditLog.EventType.LOGIN_ATTEMPT,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        details="Authentication successful.",
    )

    # Clear any lingering Django auth session (admin) to prevent session cross-contamination
    if request.user.is_authenticated:
        logout(request)

    # Store authenticated student in session
    request.session["authenticated_student_id"] = str(student.id)
    request.session["student_id"] = student.student_id

    return JsonResponse(
        {
            "success": True,
            "student_id": student.student_id,
            "full_name": student.full_name,
            "college": student.college,
            "is_admin": student.is_admin,
        },
        status=200,
    )


@require_POST
@csrf_protect
def student_logout(request: Any) -> JsonResponse:
    """
    End the current session.

    POST /api/auth/logout/
    Returns JSON: {"success": true, "message": "Logged out successfully."}
    """
    request.session.flush()
    return JsonResponse(
        {"success": True, "message": "Logged out successfully."},
        status=200,
    )


# ---------------------------------------------------------------------------
# Admin authentication (Bundle 01)
# ---------------------------------------------------------------------------

GENERIC_ADMIN_AUTH_ERROR: str = "Invalid admin credentials."


@require_POST
@csrf_protect
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def admin_login(request: Any) -> JsonResponse:
    """
    Authenticate an admin user by username + password.

    POST /api/admin/auth/login/
    Body (JSON): {"username": "...", "password": "..."}

    Returns:
        200: {"success": true, "username": "...", "role": "...", "display_name": "..."}
        400: missing fields
        401: invalid credentials / inactive profile
        429: rate limited
    """
    ip_address: str = get_client_ip(request)
    user_agent: str = get_user_agent(request)

    try:
        if request.content_type == "application/json":
            body: Dict[str, Any] = json.loads(request.body)
        else:
            body = request.POST.dict()
    except (json.JSONDecodeError, Exception):
        return JsonResponse(
            {"success": False, "error": "Invalid request body."}, status=400
        )

    username: Optional[str] = body.get("username")
    password: Optional[str] = body.get("password")

    if not username or not password:
        return JsonResponse(
            {"success": False, "error": "username and password are required."},
            status=400,
        )

    # Authenticate via Django auth
    user = authenticate(request, username=username, password=password)

    if user is None:
        AuditService.log_event(
            student_id_attempted=username,
            event_type=AuditLog.EventType.ADMIN_LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details="Invalid admin credentials.",
        )
        return JsonResponse(
            {"success": False, "error": GENERIC_ADMIN_AUTH_ERROR}, status=401
        )

    # Check for active admin profile
    try:
        profile = AdminProfile.objects.get(user=user, is_active=True)
    except AdminProfile.DoesNotExist:
        AuditService.log_event(
            student_id_attempted=username,
            event_type=AuditLog.EventType.ADMIN_LOGIN_ATTEMPT,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details="User has no active admin profile.",
        )
        return JsonResponse(
            {"success": False, "error": GENERIC_ADMIN_AUTH_ERROR}, status=401
        )

    # Log in via Django auth (sets session)
    login(request, user)

    # Clear any lingering student session keys to prevent session cross-contamination
    request.session.pop("authenticated_student_id", None)
    request.session.pop("student_id", None)

    AuditService.log_event(
        student_id_attempted=username,
        event_type=AuditLog.EventType.ADMIN_LOGIN_ATTEMPT,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        details=f"Admin login successful. Role: {profile.get_role_display()}.",
    )

    return JsonResponse(
        {
            "success": True,
            "username": user.username,
            "role": profile.role,
            "role_display": profile.get_role_display(),
            "display_name": profile.display_name,
        },
        status=200,
    )


@require_POST
@csrf_protect
def admin_logout(request: Any) -> JsonResponse:
    """
    End the admin session.

    POST /api/admin/auth/logout/
    """
    ip_address: str = get_client_ip(request)
    user_agent: str = get_user_agent(request)

    username = "unknown"
    if request.user.is_authenticated:
        username = request.user.username
        AuditService.log_event(
            student_id_attempted=username,
            event_type=AuditLog.EventType.ADMIN_LOGOUT,
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
            details="Admin logged out.",
        )

    logout(request)
    return JsonResponse(
        {"success": True, "message": "Admin logged out successfully."},
        status=200,
    )
