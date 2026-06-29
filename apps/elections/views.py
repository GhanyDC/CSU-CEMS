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
from apps.elections.scope import (
    college_matches,
    filter_candidates_for_voter,
    position_visible_to_voter,
)
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

        voter_college = ev.college_snapshot or student.college or ""

        # College election: enforce college match using the frozen roll snapshot
        if e.is_college and not college_matches(e.college, voter_college):
            continue

        elections.append(e)

    return elections


def _get_eligible_voter(student, election):
    """Return the student's frozen voter-roll entry for this election, if any."""
    return (
        EligibleVoter.objects
        .filter(election=election, student=student)
        .only("college_snapshot")
        .first()
    )


def _get_voter_college(student, election) -> str:
    """Return the college to use for election scoping."""
    eligible_voter = _get_eligible_voter(student, election)
    if eligible_voter and eligible_voter.college_snapshot:
        return eligible_voter.college_snapshot
    return student.college or ""


def _check_student_eligible(student, election):
    """
    Check if a student is eligible for a specific election.
    Returns (is_eligible, error_message).
    """
    eligible_voter = _get_eligible_voter(student, election)
    if eligible_voter is None:
        return False, "You are not on the approved voter roll for this election."

    voter_college = eligible_voter.college_snapshot or student.college or ""
    if election.is_college and not college_matches(election.college, voter_college):
        return False, "You are not eligible for this college's election."

    return True, None


def _has_voted(student, election):
    """Check if student has already cast a ballot in this election."""
    hashed = Ballot.hash_student_id(student.student_id, str(election.pk))
    return Ballot.objects.filter(
        election=election, hashed_student_id=hashed
    ).exists()


def _get_turnout_summary(election):
    """Return the student-safe turnout summary for an election."""
    turnout = TurnoutService.compute_turnout(election)
    return {
        "total_eligible": turnout["total_eligible"],
        "total_voted": turnout["total_voted"],
        "turnout_percentage": turnout["turnout_percentage"],
        "generated_at": turnout.get("generated_at"),
    }


def _serialize_position_for_voter(position, election, voter_college):
    """Serialize a position with only candidates this voter may select."""
    if not position_visible_to_voter(election, position, voter_college):
        return None

    candidates = list(
        Candidate.objects
        .filter(position=position, is_active=True)
        .order_by("full_name")
    )
    candidates = filter_candidates_for_voter(
        election,
        position,
        candidates,
        voter_college,
    )

    return {
        "id": str(position.pk),
        "title": position.title,
        "category": position.category,
        "category_display": position.get_category_display(),
        "scope_college": position.scope_college,
        "max_selections": position.max_selections,
        "single_candidate_threshold_applies": len(candidates) == 1,
        "candidates": [
            {
                "id": str(candidate.pk),
                "full_name": candidate.full_name,
                "party": candidate.party,
                "college": candidate.college or "",
                "photo_url": candidate.photo.url if candidate.photo else None,
                "platform_text": candidate.platform_text,
            }
            for candidate in candidates
        ],
    }


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
            "turnout": _get_turnout_summary(e),
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
    voter_college = _get_voter_college(student, election)

    positions = (
        Position.objects
        .filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        pos_data = _serialize_position_for_voter(pos, election, voter_college)
        if pos_data:
            positions_data.append(pos_data)

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
        "turnout": _get_turnout_summary(election),
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
    voter_college = _get_voter_college(student, election)
    positions = (
        Position.objects
        .filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        pos_data = _serialize_position_for_voter(pos, election, voter_college)
        if pos_data:
            positions_data.append(pos_data)

    return JsonResponse({
        "success": True,
        "election": {
            "id": str(election.pk),
            "name": election.name,
            "election_type": election.election_type,
            "start_time": election.start_time.isoformat(),
            "end_time": election.end_time.isoformat(),
            "turnout": _get_turnout_summary(election),
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
            "turnout": _get_turnout_summary(e),
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
        "turnout": _get_turnout_summary(first),
        "elections": elections_status,
    })


@require_GET
@login_required_student
def election_turnout_student(request, election_id):
    """
    GET /api/elections/<election_id>/turnout/

    Returns turnout only for an eligible student, without any candidate tallies.
    """
    student = request.student

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
            {"success": False, "error": "Turnout is not available for this election yet."},
            status=403,
        )

    eligible, error = _check_student_eligible(student, election)
    if not eligible:
        return JsonResponse(
            {"success": False, "error": error}, status=403
        )

    return JsonResponse({
        "success": True,
        "election": {
            "id": str(election.pk),
            "name": election.name,
            "status": election.status,
        },
        "turnout": _get_turnout_summary(election),
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
    # Student-facing results stay combined-only even for hybrid elections.
    for pos_data in results.get("positions", []):
        pos_data.pop("online_total_votes", None)
        pos_data.pop("onsite_total_votes", None)
        pos_data.pop("combined_total_votes", None)
        pos_data.pop("counting_mode", None)
        pos_data.pop("participation_note", None)
        for row in pos_data.get("results", []):
            row.pop("online_votes", None)
            row.pop("onsite_votes", None)
            row.pop("combined_votes", None)
    results.pop("online_ballots", None)
    results.pop("onsite_ballots", None)
    results.pop("combined_ballots", None)
    results.pop("counting_mode", None)
    results.pop("hybrid", None)
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
)
def election_tally_review(request, election_id):
    """
    GET /api/admin/elections/<election_id>/tally/

    Returns tally data for an election with role-based visibility:
    - EB Head: full candidate tally during Active, Closed, Published
    - Tally Watcher: participation summary during Active; full tally after Closed/Published
    - Operator: participation summary only (no per-candidate votes) in all non-draft states
    """
    try:
        election = Election.objects.get(pk=election_id)
    except (Election.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )

    if election.status == Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "No tally data for draft elections."},
            status=403,
        )

    role = request.admin_profile.role

    # --- Helper: strip per-candidate votes for participation-only view ---
    def _redact_results(results, reason):
        for pos_data in results.get("positions", []):
            for r in pos_data.get("results", []):
                r.pop("votes", None)
                r.pop("online_votes", None)
                r.pop("onsite_votes", None)
                r.pop("combined_votes", None)
            pos_data.pop("winner", None)
            pos_data.pop("status", None)
            pos_data.pop("online_total_votes", None)
            pos_data.pop("onsite_total_votes", None)
            pos_data.pop("combined_total_votes", None)
        results["redacted"] = True
        results["redacted_reason"] = reason
        return results

    # Operator: always participation summary only (no per-candidate votes)
    if role == AdminRole.ELECTORAL_BOARD_OPERATOR:
        results = ResultService.compute_results_with_thresholds(election)
        _redact_results(results, "Operator role — per-candidate tallies not available.")
        return JsonResponse({"success": True, **results})

    # Tally Watcher: participation summary during Active; full tally after Closed
    if role == AdminRole.TALLY_WATCHER and election.status == Election.Status.ACTIVE:
        results = ResultService.compute_results_with_thresholds(election)
        _redact_results(results, "Tally Watcher — per-candidate tallies available after election is closed.")
        return JsonResponse({"success": True, **results})

    # EB Head always gets full tally; Tally Watcher gets full tally after Closed/Published
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

