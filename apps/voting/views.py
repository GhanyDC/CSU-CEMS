"""
Voting views — ballot submission endpoint.
"""
import json
import logging
import uuid as uuid_mod

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.accounts.decorators import login_required_student
from apps.accounts.utils import get_client_ip
from apps.elections.models import Election
from apps.voting.services import (
    BallotAlreadyCastError,
    BallotService,
    ElectionNotActiveError,
    InvalidSelectionError,
    VoterNotEligibleError,
)

logger = logging.getLogger("cems.application")


@require_POST
@csrf_protect
@login_required_student
def cast_ballot(request):
    """
    POST /api/voting/cast/

    Body (JSON):
    {
        "election_id": "...",
        "selections": [
            {"position_id": "...", "candidate_id": "..."},
            ...
        ]
    }

    Returns:
        201: {"success": true, "ballot_id": "..."}
        400: validation errors
        409: duplicate ballot or election not active
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse(
            {"success": False, "error": "Invalid request body."}, status=400
        )

    election_id = body.get("election_id")
    raw_selections = body.get("selections")

    if not election_id:
        return JsonResponse(
            {"success": False, "error": "election_id is required."}, status=400
        )
    if not raw_selections or not isinstance(raw_selections, list):
        return JsonResponse(
            {"success": False, "error": "selections must be a non-empty list."},
            status=400,
        )

    # Parse selections into (position_id, candidate_id) tuples
    selections = []
    for item in raw_selections:
        pos_id = item.get("position_id") if isinstance(item, dict) else None
        cand_id = item.get("candidate_id") if isinstance(item, dict) else None
        if not pos_id or not cand_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Each selection must have position_id and candidate_id.",
                },
                status=400,
            )
        selections.append((str(pos_id), str(cand_id)))

    # Fetch election
    try:
        uuid_mod.UUID(str(election_id))
    except (ValueError, AttributeError):
        return JsonResponse(
            {"success": False, "error": "Invalid election_id format."}, status=400
        )

    try:
        election = Election.objects.get(pk=election_id)
    except Election.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    # Cast ballot
    try:
        ballot = BallotService.cast_ballot(
            student=request.student,
            election=election,
            selections=selections,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except ElectionNotActiveError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=409)
    except VoterNotEligibleError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)
    except BallotAlreadyCastError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=409)
    except InvalidSelectionError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse(
        {
            "success": True,
            "ballot_id": str(ballot.pk),
            "message": "Your ballot has been recorded successfully.",
        },
        status=201,
    )
