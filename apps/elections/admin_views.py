"""
Admin election setup views — JSON API endpoints for the admin election setup workflow.

All endpoints require admin authentication.
Setup actions (create, import, candidate management) require Operator or EB Head role.
Voter roll finalization requires EB Head role only.
"""
import csv
import io
import json
import logging

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import admin_login_required, role_required
from apps.accounts.models import AdminRole
from apps.elections.models import Candidate, Election, Position
from apps.elections.services import VoterRollError, VoterRollService
from apps.elections.setup_services import (
    CandidateManagementService,
    ElectionSetupError,
    ElectionSetupService,
    ReadinessService,
)

logger = logging.getLogger("cems.application")

# Roles allowed for setup operations (create, import, candidate management)
SETUP_ROLES = (AdminRole.ELECTORAL_BOARD_HEAD, AdminRole.ELECTORAL_BOARD_OPERATOR)


def _parse_json_body(request):
    """Parse JSON body from request. Returns (data, error_response)."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse(
            {"success": False, "error": "Invalid JSON body."},
            status=400,
        )


def _get_election_or_404(election_id):
    """Fetch election by UUID. Returns (election, error_response)."""
    try:
        return Election.objects.get(pk=election_id), None
    except (Election.DoesNotExist, ValueError, ValidationError):
        return None, JsonResponse(
            {"success": False, "error": "Election not found."},
            status=404,
        )


def _serialize_election_summary(election):
    """Return a compact election dict for list views."""
    return {
        "id": str(election.pk),
        "name": election.name,
        "election_type": election.election_type,
        "college": election.college,
        "status": election.status,
        "start_time": election.start_time.isoformat(),
        "end_time": election.end_time.isoformat(),
        "voter_roll_finalized": election.is_voter_roll_finalized,
        "created_at": election.created_at.isoformat(),
    }


def _serialize_election_detail(election):
    """Return a full election dict with positions, candidates, voter roll summary."""
    positions = (
        Position.objects.filter(election=election)
        .order_by("order", "title")
    )

    positions_data = []
    for pos in positions:
        candidates = (
            Candidate.objects.filter(position=pos)
            .order_by("full_name")
        )
        positions_data.append({
            "id": str(pos.pk),
            "title": pos.title,
            "category": pos.category,
            "category_display": pos.get_category_display(),
            "max_selections": pos.max_selections,
            "order": pos.order,
            "candidates": [
                {
                    "id": str(c.pk),
                    "full_name": c.full_name,
                    "party": c.party,
                    "college": c.college or "",
                    "is_active": c.is_active,
                }
                for c in candidates
            ],
        })

    # Voter roll summary
    match_summary = VoterRollService.get_match_summary(election)
    approved_count = VoterRollService.get_approved_count(election)

    return {
        "id": str(election.pk),
        "name": election.name,
        "election_type": election.election_type,
        "college": election.college,
        "status": election.status,
        "start_time": election.start_time.isoformat(),
        "end_time": election.end_time.isoformat(),
        "voter_roll_finalized": election.is_voter_roll_finalized,
        "voter_roll_finalized_by": election.voter_roll_finalized_by,
        "voter_roll_finalized_at": (
            election.voter_roll_finalized_at.isoformat()
            if election.voter_roll_finalized_at else None
        ),
        "created_at": election.created_at.isoformat(),
        "positions": positions_data,
        "voter_roll_summary": {
            **match_summary,
            "approved": approved_count,
        },
    }


# ---------------------------------------------------------------------------
# Election list and detail
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER, AdminRole.AUDITOR)
def list_elections(request):
    """
    GET /api/admin/elections/setup/list/

    Returns all elections ordered by creation date.
    """
    elections = Election.objects.all().order_by("-created_at")
    return JsonResponse({
        "success": True,
        "elections": [_serialize_election_summary(e) for e in elections],
    })


@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER, AdminRole.AUDITOR)
def election_detail(request, election_id):
    """
    GET /api/admin/elections/setup/<election_id>/

    Returns full election detail with positions, candidates, voter roll summary.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    return JsonResponse({
        "success": True,
        "election": _serialize_election_detail(election),
    })


# ---------------------------------------------------------------------------
# Election creation
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def create_campus_election(request):
    """
    POST /api/admin/elections/setup/create-campus/
    Body: {"name": "...", "start_time": "ISO", "end_time": "ISO"}

    Creates a campus election with template positions.
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    name = data.get("name", "")
    start_time_str = data.get("start_time", "")
    end_time_str = data.get("end_time", "")

    if not name or not start_time_str or not end_time_str:
        return JsonResponse(
            {"success": False, "error": "name, start_time, and end_time are required."},
            status=400,
        )

    try:
        from django.utils.dateparse import parse_datetime
        start_time = parse_datetime(start_time_str)
        end_time = parse_datetime(end_time_str)
        if not start_time or not end_time:
            raise ValueError("Invalid datetime format")
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error": "start_time and end_time must be valid ISO datetime strings."},
            status=400,
        )

    try:
        election = ElectionSetupService.create_campus_election(name, start_time, end_time)
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Campus election '{election.name}' created with {election.positions.count()} positions.",
        "election": _serialize_election_summary(election),
    }, status=201)


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def create_college_elections(request):
    """
    POST /api/admin/elections/setup/create-college/
    Body: {"name_prefix": "...", "start_time": "ISO", "end_time": "ISO", "colleges": [...] (optional)}

    Bulk-creates college elections for specified or all 9 colleges.
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    name_prefix = data.get("name_prefix", "")
    start_time_str = data.get("start_time", "")
    end_time_str = data.get("end_time", "")
    colleges = data.get("colleges", None)

    if not name_prefix or not start_time_str or not end_time_str:
        return JsonResponse(
            {"success": False, "error": "name_prefix, start_time, and end_time are required."},
            status=400,
        )

    try:
        from django.utils.dateparse import parse_datetime
        start_time = parse_datetime(start_time_str)
        end_time = parse_datetime(end_time_str)
        if not start_time or not end_time:
            raise ValueError("Invalid datetime format")
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error": "start_time and end_time must be valid ISO datetime strings."},
            status=400,
        )

    try:
        elections = ElectionSetupService.create_college_elections(
            name_prefix, start_time, end_time, colleges,
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Created {len(elections)} college election(s).",
        "elections": [_serialize_election_summary(e) for e in elections],
    }, status=201)


# ---------------------------------------------------------------------------
# Candidate management
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def add_candidate(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/candidates/add/
    Body: {"position_id": "...", "full_name": "...", "party": "...", "college": "..."}
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    data, err = _parse_json_body(request)
    if err:
        return err

    position_id = data.get("position_id", "")
    if not position_id:
        return JsonResponse(
            {"success": False, "error": "position_id is required."},
            status=400,
        )

    try:
        position = Position.objects.get(pk=position_id, election=election)
    except (Position.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Position not found in this election."},
            status=404,
        )

    try:
        candidate = CandidateManagementService.add_candidate(
            position=position,
            full_name=data.get("full_name", ""),
            party=data.get("party", ""),
            college=data.get("college", ""),
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Candidate '{candidate.full_name}' added to {position.title}.",
        "candidate": {
            "id": str(candidate.pk),
            "full_name": candidate.full_name,
            "party": candidate.party,
            "college": candidate.college or "",
            "is_active": candidate.is_active,
        },
    }, status=201)


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def update_candidate(request, election_id, candidate_id):
    """
    POST /api/admin/elections/setup/<election_id>/candidates/<candidate_id>/update/
    Body: {"full_name": "...", "party": "...", "college": "...", "is_active": bool}
    All fields optional.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        candidate = Candidate.objects.select_related("position__election").get(
            pk=candidate_id, position__election=election,
        )
    except (Candidate.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Candidate not found in this election."},
            status=404,
        )

    data, err = _parse_json_body(request)
    if err:
        return err

    try:
        candidate = CandidateManagementService.update_candidate(
            candidate=candidate,
            full_name=data.get("full_name"),
            party=data.get("party"),
            college=data.get("college"),
            is_active=data.get("is_active"),
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Candidate '{candidate.full_name}' updated.",
        "candidate": {
            "id": str(candidate.pk),
            "full_name": candidate.full_name,
            "party": candidate.party,
            "college": candidate.college or "",
            "is_active": candidate.is_active,
        },
    })


# ---------------------------------------------------------------------------
# Voter roll management
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def import_voter_roll(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/voter-roll/import/
    Content-Type: multipart/form-data with 'csv_file' field.

    Parses the uploaded CSV and imports verification records.
    CSV must have at least a 'student_id' column.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse(
            {"success": False, "error": "csv_file is required."},
            status=400,
        )

    # Validate file size (max 5 MB)
    if csv_file.size > 5 * 1024 * 1024:
        return JsonResponse(
            {"success": False, "error": "File too large. Maximum size is 5 MB."},
            status=400,
        )

    try:
        content = csv_file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as e:
        return JsonResponse(
            {"success": False, "error": f"Could not parse CSV: {e}"},
            status=400,
        )

    if not rows:
        return JsonResponse(
            {"success": False, "error": "CSV file contains no data rows."},
            status=400,
        )

    # Verify student_id column exists
    if "student_id" not in (rows[0].keys() if rows else []):
        return JsonResponse(
            {"success": False, "error": "CSV must have a 'student_id' column."},
            status=400,
        )

    try:
        summary = VoterRollService.import_verification(election, rows)
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": (
            f"Import complete: {summary['created']} created, "
            f"{summary['matched']} matched, {summary['unmatched']} unmatched, "
            f"{summary['skipped_duplicate']} duplicates skipped."
        ),
        "summary": summary,
    })


@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER, AdminRole.AUDITOR)
def voter_roll_summary(request, election_id):
    """
    GET /api/admin/elections/setup/<election_id>/voter-roll/summary/

    Returns voter roll match summary and approved counts.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    match_summary = VoterRollService.get_match_summary(election)
    approved_count = VoterRollService.get_approved_count(election)
    by_college = VoterRollService.get_approved_count_by_college(election)

    unmatched = VoterRollService.get_unmatched_records(election)
    unmatched_list = [
        {
            "student_id_input": r.student_id_input,
            "full_name_input": r.full_name_input,
            "college_input": r.college_input,
        }
        for r in unmatched[:50]  # Limit to 50 for performance
    ]

    return JsonResponse({
        "success": True,
        "match_summary": match_summary,
        "approved_count": approved_count,
        "approved_by_college": by_college,
        "unmatched_records": unmatched_list,
        "unmatched_total": unmatched.count(),
        "finalized": election.is_voter_roll_finalized,
        "finalized_by": election.voter_roll_finalized_by,
        "finalized_at": (
            election.voter_roll_finalized_at.isoformat()
            if election.voter_roll_finalized_at else None
        ),
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def generate_voter_roll(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/voter-roll/generate/

    Generates EligibleVoter records from matched verification records.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        count = VoterRollService.generate_voter_roll(election)
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    total = VoterRollService.get_approved_count(election)
    return JsonResponse({
        "success": True,
        "message": f"{count} new eligible voter(s) added. Total: {total}.",
        "new_count": count,
        "total_count": total,
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def finalize_voter_roll(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/voter-roll/finalize/

    Locks the voter roll. Only the Electoral Board Head may perform this action.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        VoterRollService.finalize_voter_roll(
            election,
            finalized_by=request.admin_profile.display_name,
        )
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    election.refresh_from_db()
    return JsonResponse({
        "success": True,
        "message": "Voter roll finalized successfully.",
        "finalized_by": election.voter_roll_finalized_by,
        "finalized_at": election.voter_roll_finalized_at.isoformat(),
    })


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER, AdminRole.AUDITOR)
def readiness_check(request, election_id):
    """
    GET /api/admin/elections/setup/<election_id>/readiness/

    Returns a structured readiness report for the election.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    report = ReadinessService.check_readiness(election)
    return JsonResponse({"success": True, **report})
