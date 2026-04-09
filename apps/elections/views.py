"""
Elections views — student eligibility, ballot rendering, lifecycle management,
results, and monitoring endpoints.
"""
import json
import logging
import uuid as uuid_mod

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import (
    admin_login_required,
    login_required_student,
    role_required,
)
from apps.accounts.models import AdminRole
from apps.accounts.utils import get_client_ip
from apps.elections.models import Candidate, College, Election, EligibleVoter, Position
from apps.elections.services import (
    ElectionLifecycleService,
    ElectionNotReadyError,
    InvalidTransitionError,
    ResultService,
    TurnoutService,
)
from apps.voting.models import Ballot

logger = logging.getLogger("cems.application")


# ---------------------------------------------------------------------------
# Student eligibility helpers
# ---------------------------------------------------------------------------

def _get_eligible_elections(student):
    """
    Return elections the student is on the voter roll for, filtered
    to only Active or Published elections.

    Rules:
    - Campus election: eligible if student is on that election's voter roll
    - College election: eligible only if student is on voter roll AND
      the election's college matches the student's college
    """
    eligible_entries = (
        EligibleVoter.objects
        .filter(student=student)
        .select_related("election")
    )

    elections = []
    for ev in eligible_entries:
        e = ev.election
        # Only show Active (can vote) or Published (can see results) elections
        if e.status not in (Election.Status.ACTIVE, Election.Status.PUBLISHED):
            continue

        # College election: enforce college match
        if e.is_college and e.college != student.college:
            continue

        elections.append(e)

    return elections


def _check_student_eligible(student, election):
    """
    Check if a student is eligible for a specific election.
    Returns (is_eligible, error_message).
    """
    if not EligibleVoter.objects.filter(
        election=election, student=student
    ).exists():
        return False, "You are not on the approved voter roll for this election."

    if election.is_college and election.college != student.college:
        return False, "You are not eligible for this college's election."

    return True, None


def _has_voted(student, election):
    """Check if student has already cast a ballot in this election."""
    hashed = Ballot.hash_student_id(student.student_id, str(election.pk))
    return Ballot.objects.filter(
        election=election, hashed_student_id=hashed
    ).exists()


# ---------------------------------------------------------------------------
# Student-facing endpoints
# ---------------------------------------------------------------------------

@require_GET
@login_required_student
def my_elections(request):
    """
    GET /api/elections/mine/

    Returns elections the logged-in student is eligible for.
    Shows Active elections (can vote) and Published elections (can see results).
    Includes voting status for each.
    """
    student = request.student
    elections = _get_eligible_elections(student)

    elections_data = []
    for e in elections:
        voted = _has_voted(student, e)
        elections_data.append({
            "id": str(e.pk),
            "name": e.name,
            "election_type": e.election_type,
            "college": e.college,
            "status": e.status,
            "start_time": e.start_time.isoformat(),
            "end_time": e.end_time.isoformat(),
            "has_voted": voted,
        })

    return JsonResponse({
        "success": True,
        "elections": elections_data,
    })


@require_GET
@login_required_student
def election_ballot(request, election_id):
    """
    GET /api/elections/<election_id>/ballot/

    Returns the ballot structure (positions + active candidates) for voting.
    Enforces eligibility and election status checks.

    CRITICAL: For house_college positions in campus elections, only candidates
    from the student's own college are returned.
    """
    student = request.student

    try:
        election = Election.objects.get(pk=election_id)
    except (Election.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    # Must be Active to view ballot
    if election.status != Election.Status.ACTIVE:
        return JsonResponse(
            {"success": False, "error": "This election is not currently active."},
            status=403,
        )

    # Eligibility check
    eligible, error = _check_student_eligible(student, election)
    if not eligible:
        return JsonResponse(
            {"success": False, "error": error}, status=403
        )

    # Check if already voted
    voted = _has_voted(student, election)

    positions = (
        Position.objects
        .filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        candidates_qs = (
            Candidate.objects
            .filter(position=pos, is_active=True)
            .order_by("full_name")
        )

        # CRITICAL FIX: For house_college positions in campus elections,
        # only show candidates from the student's own college
        if pos.category == Position.Category.HOUSE_COLLEGE and election.is_campus:
            candidates_qs = candidates_qs.filter(college=student.college)
            # Skip position entirely if no candidates for this student's college
            if not candidates_qs.exists():
                continue

        positions_data.append({
            "id": str(pos.pk),
            "title": pos.title,
            "category": pos.category,
            "category_display": pos.get_category_display(),
            "max_selections": pos.max_selections,
            "candidates": [
                {
                    "id": str(c.pk),
                    "full_name": c.full_name,
                    "party": c.party,
                    "college": c.college or "",
                    "photo_url": c.photo.url if c.photo else None,
                    "platform_text": c.platform_text,
                }
                for c in candidates_qs
            ],
        })

    return JsonResponse({
        "success": True,
        "election": {
            "id": str(election.pk),
            "name": election.name,
            "election_type": election.election_type,
            "college": election.college,
            "start_time": election.start_time.isoformat(),
            "end_time": election.end_time.isoformat(),
        },
        "has_voted": voted,
        "positions": positions_data,
    })


@require_GET
@login_required_student
def current_election(request):
    """
    GET /api/elections/current/

    Returns the currently active election with its positions and candidates.
    Now filters by student eligibility and college scope.
    """
    student = request.student
    elections = _get_eligible_elections(student)

    # Find the first active election the student is eligible for
    active = [e for e in elections if e.status == Election.Status.ACTIVE]
    if not active:
        return JsonResponse(
            {"success": False, "error": "No active election at this time."},
            status=404,
        )

    election = active[0]
    positions = (
        Position.objects
        .filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        candidates_qs = (
            Candidate.objects
            .filter(position=pos, is_active=True)
            .order_by("full_name")
        )

        # College representative filtering for campus elections
        if pos.category == Position.Category.HOUSE_COLLEGE and election.is_campus:
            candidates_qs = candidates_qs.filter(college=student.college)
            if not candidates_qs.exists():
                continue

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
                    "photo_url": c.photo.url if c.photo else None,
                    "platform_text": c.platform_text,
                }
                for c in candidates_qs
            ],
        })

    return JsonResponse({
        "success": True,
        "election": {
            "id": str(election.pk),
            "name": election.name,
            "election_type": election.election_type,
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

    Returns voting status for all eligible elections.
    """
    student = request.student
    elections = _get_eligible_elections(student)

    active_elections = [e for e in elections if e.status == Election.Status.ACTIVE]

    if not active_elections:
        return JsonResponse({
            "success": True,
            "has_active_election": False,
            "has_voted": False,
            "elections": [],
        })

    elections_status = []
    for e in active_elections:
        voted = _has_voted(student, e)
        elections_status.append({
            "election_id": str(e.pk),
            "election_name": e.name,
            "election_type": e.election_type,
            "has_voted": voted,
        })

    # Backward compatibility: return first election info at top level
    first = active_elections[0]
    first_voted = _has_voted(student, first)

    return JsonResponse({
        "success": True,
        "has_active_election": True,
        "election_id": str(first.pk),
        "election_name": first.name,
        "has_voted": first_voted,
        "elections": elections_status,
    })


# ---------------------------------------------------------------------------
# Results endpoints
# ---------------------------------------------------------------------------

@require_GET
@login_required_student
def election_results(request, election_id=None):
    """
    GET /api/elections/results/
    GET /api/elections/results/<election_id>/

    Returns results for a published election.
    Students may only view results of elections they are eligible for,
    and only after the election is Published.
    """
    student = request.student

    if election_id:
        try:
            election = Election.objects.get(pk=election_id)
        except Election.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Election not found."}, status=404
            )
    else:
        # Find the most recent published election the student is eligible for
        eligible_election_ids = (
            EligibleVoter.objects
            .filter(student=student)
            .values_list("election_id", flat=True)
        )
        election = (
            Election.objects
            .filter(pk__in=eligible_election_ids, status=Election.Status.PUBLISHED)
            .order_by("-updated_at")
            .first()
        )
        if not election:
            return JsonResponse(
                {"success": False, "error": "No published results available."},
                status=404,
            )

    # Students can only see Published results
    if election.status != Election.Status.PUBLISHED:
        return JsonResponse(
            {"success": False, "error": "Results are not yet published."},
            status=403,
        )

    # Eligibility check — student must be on the voter roll
    eligible, error = _check_student_eligible(student, election)
    if not eligible:
        return JsonResponse(
            {"success": False, "error": error}, status=403
        )

    results = ResultService.compute_results_with_thresholds(election)
    return JsonResponse({"success": True, **results})


# ---------------------------------------------------------------------------
# Admin monitoring endpoints
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(
    AdminRole.ELECTORAL_BOARD_HEAD,
    AdminRole.ELECTORAL_BOARD_OPERATOR,
    AdminRole.TALLY_WATCHER,
    AdminRole.AUDITOR,
)
def election_turnout(request, election_id):
    """
    GET /api/admin/elections/<election_id>/turnout/

    Returns turnout statistics for an election. Available during Active status.
    Does NOT expose per-candidate tallies.
    """
    try:
        election = Election.objects.get(pk=election_id)
    except (Election.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    if election.status not in (
        Election.Status.ACTIVE,
        Election.Status.CLOSED,
        Election.Status.PUBLISHED,
    ):
        return JsonResponse(
            {"success": False, "error": "Turnout data is not available for draft elections."},
            status=403,
        )

    turnout = TurnoutService.compute_turnout(election)
    return JsonResponse({"success": True, **turnout})


@require_GET
@admin_login_required
@role_required(
    AdminRole.ELECTORAL_BOARD_HEAD,
    AdminRole.ELECTORAL_BOARD_OPERATOR,
    AdminRole.TALLY_WATCHER,
    AdminRole.AUDITOR,
)
def election_tally_review(request, election_id):
    """
    GET /api/admin/elections/<election_id>/tally/

    Returns full tally (candidate vote counts) for an election.
    Available only after Close (Closed or Published status).
    NOT available during Active voting — no live candidate tallies.
    """
    try:
        election = Election.objects.get(pk=election_id)
    except (Election.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    if election.status == Election.Status.ACTIVE:
        return JsonResponse(
            {"success": False, "error": "Candidate tallies are not available during active voting."},
            status=403,
        )

    if election.status == Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "No tally data for draft elections."},
            status=403,
        )

    results = ResultService.compute_results_with_thresholds(election)
    return JsonResponse({"success": True, **results})


# ---------------------------------------------------------------------------
# Admin lifecycle endpoints (Electoral Board Head only)
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def start_election(request):
    """
    POST /api/admin/elections/start/
    Body: {"election_id": "..."}

    Transitions an election from DRAFT to ACTIVE.
    Only the Electoral Board Head may perform this action.
    """
    return _lifecycle_action(request, ElectionLifecycleService.start_election)


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def close_election(request):
    """
    POST /api/admin/elections/close/
    Body: {"election_id": "..."}

    Transitions an election from ACTIVE to CLOSED.
    Only the Electoral Board Head may perform this action.
    """
    return _lifecycle_action(request, ElectionLifecycleService.close_election)


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def publish_results(request):
    """
    POST /api/admin/elections/publish/
    Body: {"election_id": "..."}

    Transitions an election from CLOSED to PUBLISHED.
    Only the Electoral Board Head may perform this action.
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

    try:
        election = action_method(
            election,
            performed_by=request.admin_profile.user.username,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except InvalidTransitionError as e:
        return JsonResponse(
            {"success": False, "error": str(e)}, status=409
        )
    except ElectionNotReadyError as e:
        return JsonResponse(
            {"success": False, "error": str(e)}, status=409
        )

    return JsonResponse({
        "success": True,
        "election_id": str(election.pk),
        "status": election.status,
    })


# ---------------------------------------------------------------------------
# Public stats (used on the student login page)
# ---------------------------------------------------------------------------

@require_GET
def site_stats(request):
    """
    GET /api/stats/ — returns public counters shown on the login page.
    No authentication required.
    """
    colleges = College.objects.filter(is_active=True).count()
    elections_held = Election.objects.filter(
        status__in=[Election.Status.CLOSED, Election.Status.PUBLISHED]
    ).count()
    return JsonResponse({"colleges": colleges, "elections_held": elections_held})

