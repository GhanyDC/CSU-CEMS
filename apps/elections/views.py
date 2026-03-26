"""
Elections views — election info, lifecycle management, and results endpoints.
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import login_required_student
from apps.elections.models import Election, Position, Candidate
from apps.elections.services import (
    ElectionLifecycleService,
    InvalidTransitionError,
    ResultService,
)
from apps.voting.models import Ballot

logger = logging.getLogger("cems.application")


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


# ---------------------------------------------------------------------------
# Public / Student endpoints
# ---------------------------------------------------------------------------

@require_GET
@login_required_student
def current_election(request):
    """
    GET /api/elections/current/

    Returns the currently active election with its positions and candidates.
    """
    election = (
        Election.objects
        .filter(status=Election.Status.ACTIVE)
        .first()
    )
    if not election:
        return JsonResponse(
            {"success": False, "error": "No active election at this time."},
            status=404,
        )

    positions = (
        Position.objects
        .filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        candidates = (
            Candidate.objects
            .filter(position=pos, is_active=True)
            .order_by("full_name")
        )
        positions_data.append({
            "id": str(pos.pk),
            "title": pos.title,
            "category": pos.category,
            "max_selections": pos.max_selections,
            "candidates": [
                {
                    "id": str(c.pk),
                    "full_name": c.full_name,
                    "party": c.party,
                    "college": c.college,
                }
                for c in candidates
            ],
        })

    return JsonResponse({
        "success": True,
        "election": {
            "id": str(election.pk),
            "name": election.name,
            "start_time": election.start_time.isoformat(),
            "end_time": election.end_time.isoformat(),
            "positions": positions_data,
        },
    })


@require_GET
@login_required_student
def voting_status(request):
    """
    GET /api/elections/status/

    Returns whether the authenticated student has already voted in the current election.
    """
    election = (
        Election.objects
        .filter(status=Election.Status.ACTIVE)
        .first()
    )
    if not election:
        return JsonResponse({
            "success": True,
            "has_active_election": False,
            "has_voted": False,
        })

    hashed = Ballot.hash_student_id(request.student.student_id, str(election.pk))
    has_voted = Ballot.objects.filter(
        election=election, hashed_student_id=hashed
    ).exists()

    return JsonResponse({
        "success": True,
        "has_active_election": True,
        "election_id": str(election.pk),
        "election_name": election.name,
        "has_voted": has_voted,
    })


# ---------------------------------------------------------------------------
# Results endpoint (published elections only)
# ---------------------------------------------------------------------------

@require_GET
@login_required_student
def election_results(request, election_id=None):
    """
    GET /api/elections/results/
    GET /api/elections/results/<election_id>/

    Returns results for a published election.
    """
    if election_id:
        try:
            election = Election.objects.get(pk=election_id)
        except Election.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Election not found."}, status=404
            )
    else:
        election = (
            Election.objects
            .filter(status=Election.Status.PUBLISHED)
            .first()
        )
        if not election:
            return JsonResponse(
                {"success": False, "error": "No published results available."},
                status=404,
            )

    if election.status != Election.Status.PUBLISHED:
        return JsonResponse(
            {"success": False, "error": "Results are not yet published."},
            status=403,
        )

    results = ResultService.compute_results(election)
    return JsonResponse({"success": True, **results})


# ---------------------------------------------------------------------------
# Admin lifecycle endpoints
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@login_required_student
def start_election(request):
    """
    POST /api/admin/elections/start/
    Body: {"election_id": "..."}

    Transitions an election from DRAFT to ACTIVE.
    """
    return _lifecycle_action(request, ElectionLifecycleService.start_election)


@require_POST
@csrf_protect
@login_required_student
def close_election(request):
    """
    POST /api/admin/elections/close/
    Body: {"election_id": "..."}

    Transitions an election from ACTIVE to CLOSED.
    """
    return _lifecycle_action(request, ElectionLifecycleService.close_election)


@require_POST
@csrf_protect
@login_required_student
def publish_results(request):
    """
    POST /api/admin/elections/publish/
    Body: {"election_id": "..."}

    Transitions an election from CLOSED to PUBLISHED.
    """
    return _lifecycle_action(request, ElectionLifecycleService.publish_results)


def _lifecycle_action(request, action_method):
    """Shared logic for lifecycle transition endpoints."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse(
            {"success": False, "error": "Invalid request body."}, status=400
        )

    election_id = body.get("election_id")
    if not election_id:
        return JsonResponse(
            {"success": False, "error": "election_id is required."}, status=400
        )

    try:
        election = Election.objects.get(pk=election_id)
    except Election.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    try:
        election = action_method(
            election,
            performed_by=request.student.student_id,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except InvalidTransitionError as e:
        return JsonResponse(
            {"success": False, "error": str(e)}, status=409
        )

    return JsonResponse({
        "success": True,
        "election_id": str(election.pk),
        "status": election.status,
    })
