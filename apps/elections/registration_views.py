"""Student-facing web voter registration endpoints."""

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import login_required_student
from apps.accounts.utils import get_client_ip, get_user_agent
from apps.elections.models import Election
from apps.elections.services import RegistrationError, WebVoterRegistrationService


def _get_election_or_404(election_id):
    try:
        return Election.objects.select_related("school_year").get(pk=election_id), None
    except (Election.DoesNotExist, ValueError, ValidationError):
        return None, JsonResponse(
            {"success": False, "error": "Election not found."},
            status=404,
        )


@require_GET
@login_required_student
def available_registrations(request):
    """GET /api/registration/available/"""
    elections = WebVoterRegistrationService.available_elections_for_student(
        request.student,
    )
    return JsonResponse({"success": True, "elections": elections})


@require_GET
@login_required_student
def registration_status(request, election_id):
    """GET /api/registration/elections/<election_id>/status/"""
    election, err = _get_election_or_404(election_id)
    if err:
        return err
    return JsonResponse({
        "success": True,
        "registration": WebVoterRegistrationService.build_registration_status(
            request.student,
            election,
        ),
    })


@require_POST
@csrf_protect
@login_required_student
def register_for_election(request, election_id):
    """POST /api/registration/elections/<election_id>/register/"""
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        result = WebVoterRegistrationService.register(
            request.student,
            election,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except RegistrationError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    registration = result["registration"]
    status_code = 201 if result["created"] else 200
    return JsonResponse(
        {
            "success": True,
            "created": result["created"],
            "eligible_created": result["eligible_created"],
            "registration": {
                "id": str(registration.pk),
                "status": registration.status,
                "election_id": str(registration.election_id),
                "eligible_voter_id": str(registration.eligible_voter_id),
                "college_snapshot": registration.college_snapshot,
                "decided_at": (
                    registration.decided_at.isoformat()
                    if registration.decided_at else None
                ),
            },
        },
        status=status_code,
    )
