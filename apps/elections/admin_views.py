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

from PIL import Image

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import admin_login_required, role_required
from apps.accounts.models import AdminRole
from apps.elections.models import Candidate, College, Election, Position, RegistrarImportBatch
from apps.elections.hybrid_services import HybridElectionError, HybridElectionService
from apps.elections.services import (
    RegistrarBatchService,
    TurnoutService,
    VoterRollError,
    VoterRollService,
)
from apps.elections.setup_services import (
    CandidateManagementService,
    ElectionSetupError,
    ElectionSetupService,
    PositionManagementService,
    ReadinessService,
)

logger = logging.getLogger(__name__)

MAX_CSV_ROWS = 50_000


def _sanitize_csv_cell(value):
    """Strip formula-injection prefixes from CSV cell values."""
    if value and isinstance(value, str) and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _parse_csv_safely(csv_file, max_size_mb, max_rows=MAX_CSV_ROWS):
    """Parse a CSV upload with size, row-count, and formula-injection protections.

    Returns (rows, error_response). If error_response is not None, return it directly.
    """
    if csv_file.size > max_size_mb * 1024 * 1024:
        return None, JsonResponse(
            {"success": False, "error": f"File too large. Maximum size is {max_size_mb} MB."},
            status=400,
        )
    try:
        content = csv_file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                return None, JsonResponse(
                    {"success": False, "error": f"File has too many rows. Maximum is {max_rows:,}."},
                    status=400,
                )
            rows.append({k: _sanitize_csv_cell(v) for k, v in row.items()})
    except (UnicodeDecodeError, csv.Error) as e:
        logger.warning("CSV parse error: %s", e)
        return None, JsonResponse(
            {"success": False, "error": "CSV file is invalid or corrupt. Please check the format and try again."},
            status=400,
        )
    if not rows:
        return None, JsonResponse(
            {"success": False, "error": "CSV file contains no data rows."},
            status=400,
        )
    return rows, None

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


def _get_banner_url(election):
    banner_url = None
    if election.banner:
        try:
            banner_url = election.banner.url
        except Exception:
            banner_url = None
    return banner_url


def _serialize_election_summary(election):
    """Return a compact election dict for list views."""
    banner_url = _get_banner_url(election)
    return {
        "id": str(election.pk),
        "name": election.name,
        "election_type": election.election_type,
        "voting_mode": election.voting_mode,
        "voting_mode_display": election.get_voting_mode_display(),
        "college": election.college,
        "status": election.status,
        "start_time": election.start_time.isoformat(),
        "end_time": election.end_time.isoformat(),
        "voter_roll_finalized": election.is_voter_roll_finalized,
        "registrar_batch_id": str(election.registrar_batch_id) if election.registrar_batch_id else None,
        "registrar_batch_name": election.registrar_batch.name if election.registrar_batch_id else None,
        "created_at": election.created_at.isoformat(),
        "banner_url": banner_url,
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
                    "photo_url": c.photo.url if c.photo else None,
                    "platform_text": c.platform_text,
                }
                for c in candidates
            ],
        })

    # Voter roll summary
    match_summary = VoterRollService.get_match_summary(election)
    approved_count = VoterRollService.get_approved_count(election)

    # Turnout data (votes cast vs eligible voters)
    turnout = TurnoutService.compute_turnout(election)
    hybrid_summary = (
        HybridElectionService.build_hybrid_summary(election)
        if election.is_hybrid
        else None
    )

    return {
        "id": str(election.pk),
        "name": election.name,
        "election_type": election.election_type,
        "voting_mode": election.voting_mode,
        "voting_mode_display": election.get_voting_mode_display(),
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
        "registrar_batch_id": str(election.registrar_batch_id) if election.registrar_batch_id else None,
        "registrar_batch_name": election.registrar_batch.name if election.registrar_batch_id else None,
        "created_at": election.created_at.isoformat(),
        "positions": positions_data,
        "voter_roll_summary": {
            **match_summary,
            "approved": approved_count,
        },
        "turnout": {
            "total_eligible": turnout["total_eligible"],
            "total_voted": turnout["total_voted"],
            "turnout_percentage": turnout["turnout_percentage"],
            "online_voted": turnout["online_voted"],
            "onsite_voted": turnout["onsite_voted"],
            "combined_voted": turnout["combined_voted"],
            "online_turnout_percentage": turnout["online_turnout_percentage"],
            "onsite_turnout_percentage": turnout["onsite_turnout_percentage"],
            "combined_turnout_percentage": turnout["combined_turnout_percentage"],
            "has_official_onsite_turnout": turnout["has_official_onsite_turnout"],
            "by_college": turnout.get("by_college", []),
        },
        "banner_url": _get_banner_url(election),
        "hybrid": hybrid_summary,
    }


# ---------------------------------------------------------------------------
# Election list and detail
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
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
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
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
# Election creation helpers
# ---------------------------------------------------------------------------

def _save_election_banner(election, banner_file):
    """Validate and save a banner image. Returns an error string on failure, None on success."""
    max_size = 5 * 1024 * 1024
    if banner_file.size > max_size:
        return "Banner too large. Maximum size is 5 MB."
    try:
        banner_file.seek(0)
        img = Image.open(banner_file)
        img.verify()
        banner_file.seek(0)
    except Exception:
        return "Invalid image file. Upload a valid JPEG, PNG, or WebP image."
    allowed_formats = {"JPEG", "PNG", "WEBP"}
    img_format = Image.open(banner_file).format
    banner_file.seek(0)
    if img_format not in allowed_formats:
        return f"Invalid image format '{img_format}'. Allowed: JPEG, PNG, WebP."
    if election.banner:
        election.banner.delete(save=False)
    election.banner = banner_file
    election.save(update_fields=["banner", "updated_at"])
    return None


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
    Accepts multipart/form-data (name, start_time, end_time, optional banner file)
    or JSON body for backward compatibility.

    Creates a campus election with template positions.
    """
    content_type = request.content_type or ""
    if "application/json" in content_type:
        data, err = _parse_json_body(request)
        if err:
            return err
        name = data.get("name", "")
        start_time_str = data.get("start_time", "")
        end_time_str = data.get("end_time", "")
        voting_mode = data.get("voting_mode", Election.VotingMode.ONLINE)
        banner = None
    else:
        name = request.POST.get("name", "")
        start_time_str = request.POST.get("start_time", "")
        end_time_str = request.POST.get("end_time", "")
        voting_mode = request.POST.get("voting_mode", Election.VotingMode.ONLINE)
        banner = request.FILES.get("banner") or None

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
        election = ElectionSetupService.create_campus_election(
            name,
            start_time,
            end_time,
            voting_mode=voting_mode,
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    if banner and banner.size > 0:
        err_msg = _save_election_banner(election, banner)
        if err_msg:
            logger.warning("Banner upload failed for election %s: %s", election.pk, err_msg)

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
    Accepts multipart/form-data (name_prefix, start_time, end_time, optional banner file)
    or JSON body for backward compatibility.

    Bulk-creates college elections for specified or all 9 colleges.
    """
    content_type = request.content_type or ""
    if "application/json" in content_type:
        data, err = _parse_json_body(request)
        if err:
            return err
        name_prefix = data.get("name_prefix", "")
        start_time_str = data.get("start_time", "")
        end_time_str = data.get("end_time", "")
        colleges = data.get("colleges", None)
        voting_mode = data.get("voting_mode", Election.VotingMode.ONLINE)
        banner = None
    else:
        name_prefix = request.POST.get("name_prefix", "")
        start_time_str = request.POST.get("start_time", "")
        end_time_str = request.POST.get("end_time", "")
        colleges = None
        voting_mode = request.POST.get("voting_mode", Election.VotingMode.ONLINE)
        banner = request.FILES.get("banner") or None

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
            name_prefix,
            start_time,
            end_time,
            colleges,
            voting_mode=voting_mode,
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    # Apply banner to each created election if provided
    if banner and banner.size > 0:
        for election in elections:
            banner.seek(0)
            err_msg = _save_election_banner(election, banner)
            if err_msg:
                logger.warning("Banner upload failed for election %s: %s", election.pk, err_msg)
                break

    return JsonResponse({
        "success": True,
        "message": f"Created {len(elections)} college election(s).",
        "elections": [_serialize_election_summary(e) for e in elections],
    }, status=201)


# ---------------------------------------------------------------------------
# Election management (delete, banner)
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def delete_election(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/delete/

    Permanently deletes a DRAFT election. Active, Closed, and Published
    elections cannot be deleted.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status != Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Only draft elections can be deleted."},
            status=400,
        )

    election_name = election.name
    # Remove banner file from storage before deleting the record
    if election.banner:
        election.banner.delete(save=False)
    election.delete()

    return JsonResponse({"success": True, "message": f"Election '{election_name}' deleted."})


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def upload_election_banner(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/banner/
    Content-Type: multipart/form-data with 'banner' field.

    Upload or replace an election's banner image. Election must be in Draft.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status != Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Banner can only be changed while election is in Draft."},
            status=400,
        )

    banner = request.FILES.get("banner")
    if not banner:
        return JsonResponse({"success": False, "error": "banner file is required."}, status=400)

    err_msg = _save_election_banner(election, banner)
    if err_msg:
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    return JsonResponse({
        "success": True,
        "message": "Banner uploaded.",
        "banner_url": election.banner.url,
        "election": _serialize_election_summary(election),
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def update_election_settings(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/update/
    Body: {"voting_mode": "online"|"hybrid"}

    Updates draft-only election settings.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    data, err = _parse_json_body(request)
    if err:
        return err

    try:
        if "voting_mode" in data:
            ElectionSetupService.update_draft_election_voting_mode(
                election,
                data.get("voting_mode"),
            )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    election.refresh_from_db()
    return JsonResponse({
        "success": True,
        "message": "Election settings updated.",
        "election": _serialize_election_detail(election),
    })


# ---------------------------------------------------------------------------
# Position management (EB Head only)
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def create_position(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/positions/create/
    Body: {"title": "...", "category": "...", "max_selections": 1, "order": 0}
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    data, err = _parse_json_body(request)
    if err:
        return err

    try:
        max_sel = int(data.get("max_selections", 1))
        order = int(data.get("order", 0))
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "error": "max_selections and order must be integers."},
            status=400,
        )

    try:
        position = PositionManagementService.add_position(
            election=election,
            title=data.get("title", ""),
            category=data.get("category", ""),
            max_selections=max_sel,
            order=order,
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Position '{position.title}' created.",
        "position": {
            "id": str(position.pk),
            "title": position.title,
            "category": position.category,
            "category_display": position.get_category_display(),
            "max_selections": position.max_selections,
            "order": position.order,
        },
    }, status=201)


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def update_position(request, election_id, position_id):
    """
    POST /api/admin/elections/setup/<election_id>/positions/<position_id>/update/
    Body: {"title": "...", "category": "...", "max_selections": 1, "order": 0}
    All fields optional.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        position = Position.objects.get(pk=position_id, election=election)
    except (Position.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Position not found in this election."},
            status=404,
        )

    data, err = _parse_json_body(request)
    if err:
        return err

    max_sel = data.get("max_selections")
    order = data.get("order")
    if max_sel is not None:
        try:
            max_sel = int(max_sel)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "error": "max_selections must be an integer."},
                status=400,
            )
    if order is not None:
        try:
            order = int(order)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "error": "order must be an integer."},
                status=400,
            )

    try:
        position = PositionManagementService.update_position(
            position=position,
            title=data.get("title"),
            category=data.get("category"),
            max_selections=max_sel,
            order=order,
        )
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Position '{position.title}' updated.",
        "position": {
            "id": str(position.pk),
            "title": position.title,
            "category": position.category,
            "category_display": position.get_category_display(),
            "max_selections": position.max_selections,
            "order": position.order,
        },
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def delete_position(request, election_id, position_id):
    """
    POST /api/admin/elections/setup/<election_id>/positions/<position_id>/delete/

    Hard-deletes the position and all its candidates. Election must be in DRAFT.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    try:
        position = Position.objects.get(pk=position_id, election=election)
    except (Position.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Position not found in this election."},
            status=404,
        )

    title = position.title
    try:
        PositionManagementService.delete_position(position)
    except ElectionSetupError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Position '{title}' deleted.",
    })


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

    rows, err_resp = _parse_csv_safely(csv_file, max_size_mb=5)
    if err_resp:
        return err_resp

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
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
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
# Hybrid canvass management
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
def hybrid_summary(request, election_id):
    """GET /api/admin/elections/setup/<election_id>/hybrid/summary/"""
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    return JsonResponse({
        "success": True,
        "hybrid": HybridElectionService.build_hybrid_summary(election),
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def import_hybrid_roster(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/hybrid/roster/import/
    Content-Type: multipart/form-data with 'csv_file' field.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"success": False, "error": "csv_file is required."}, status=400)

    rows, err_resp = _parse_csv_safely(csv_file, max_size_mb=5)
    if err_resp:
        return err_resp

    try:
        result = HybridElectionService.import_onsite_roster(
            election,
            rows,
            source_filename=csv_file.name,
            imported_by=request.admin_profile.display_name,
        )
    except HybridElectionError as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "summary": e.summary,
                "hybrid": HybridElectionService.build_hybrid_summary(election),
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            **result,
            "hybrid": HybridElectionService.build_hybrid_summary(election),
        }
    )


@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
def download_hybrid_tally_template(request, election_id):
    """GET /api/admin/elections/setup/<election_id>/hybrid/tally/template/"""
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if not election.is_hybrid:
        return JsonResponse(
            {"success": False, "error": "Tally templates are only available for hybrid elections."},
            status=400,
        )
    if election.status == Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Tally templates become available after draft setup."},
            status=400,
        )

    now = timezone.now()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="hybrid_tally_template_{election.pk}_{now.strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.DictWriter(
        response,
        fieldnames=[
            "position_id",
            "position_title",
            "candidate_id",
            "candidate_name",
            "onsite_votes",
        ],
    )
    writer.writeheader()
    for row in HybridElectionService.build_tally_template_rows(election):
        writer.writerow(row)
    return response


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def import_hybrid_tally(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/hybrid/tally/import/
    Content-Type: multipart/form-data with 'csv_file' field.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"success": False, "error": "csv_file is required."}, status=400)

    rows, err_resp = _parse_csv_safely(csv_file, max_size_mb=10)
    if err_resp:
        return err_resp

    try:
        result = HybridElectionService.import_onsite_tally(
            election,
            rows,
            source_filename=csv_file.name,
            imported_by=request.admin_profile.display_name,
        )
    except HybridElectionError as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "summary": e.summary,
                "hybrid": HybridElectionService.build_hybrid_summary(election),
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            **result,
            "hybrid": HybridElectionService.build_hybrid_summary(election),
        }
    )


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
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


# ---------------------------------------------------------------------------
# Candidate photo upload
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def upload_candidate_photo(request, election_id, candidate_id):
    """
    POST /api/admin/elections/setup/<election_id>/candidates/<candidate_id>/photo/
    Content-Type: multipart/form-data with 'photo' field.

    Upload or replace a candidate's campaign photo.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status != Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Photos can only be uploaded while election is in Draft."},
            status=400,
        )

    try:
        candidate = Candidate.objects.select_related("position__election").get(
            pk=candidate_id, position__election=election,
        )
    except (Candidate.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Candidate not found in this election."},
            status=404,
        )

    photo = request.FILES.get("photo")
    if not photo:
        return JsonResponse(
            {"success": False, "error": "photo file is required."},
            status=400,
        )

    if photo.size == 0:
        return JsonResponse(
            {"success": False, "error": "Photo file is empty."},
            status=400,
        )

    # Validate file size
    max_size = getattr(settings, "CEMS_MAX_PHOTO_SIZE_MB", 2) * 1024 * 1024
    if photo.size > max_size:
        return JsonResponse(
            {"success": False, "error": f"Photo too large. Maximum size is {getattr(settings, 'CEMS_MAX_PHOTO_SIZE_MB', 2)} MB."},
            status=400,
        )

    # Validate actual image content using Pillow (magic number check)
    try:
        photo.seek(0)
        img = Image.open(photo)
        img.verify()
        photo.seek(0)
    except Exception:
        return JsonResponse(
            {"success": False, "error": "Invalid image file. Upload a valid JPEG, PNG, or WebP image."},
            status=400,
        )

    allowed_formats = {"JPEG", "PNG", "WEBP"}
    img_format = Image.open(photo).format
    photo.seek(0)
    if img_format not in allowed_formats:
        return JsonResponse(
            {"success": False, "error": f"Invalid image format '{img_format}'. Allowed: JPEG, PNG, WebP."},
            status=400,
        )

    # Delete old photo if exists
    if candidate.photo:
        candidate.photo.delete(save=False)

    candidate.photo = photo
    candidate.save(update_fields=["photo", "updated_at"])

    return JsonResponse({
        "success": True,
        "message": f"Photo uploaded for {candidate.full_name}.",
        "photo_url": candidate.photo.url,
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def delete_candidate(request, election_id, candidate_id):
    """
    POST /api/admin/elections/setup/<election_id>/candidates/<candidate_id>/delete/

    Soft-delete (deactivate) a candidate. Election must be in Draft.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status != Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Candidates can only be removed while election is in Draft."},
            status=400,
        )

    try:
        candidate = Candidate.objects.select_related("position__election").get(
            pk=candidate_id, position__election=election,
        )
    except (Candidate.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Candidate not found in this election."},
            status=404,
        )

    candidate.is_active = False
    candidate.save(update_fields=["is_active", "updated_at"])

    return JsonResponse({
        "success": True,
        "message": f"Candidate '{candidate.full_name}' deactivated.",
    })


# ---------------------------------------------------------------------------
# Registrar batch management
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
def list_registrar_batches(request):
    """
    GET /api/admin/elections/setup/registrar-batches/

    List all active registrar import batches.
    """
    include_archived = request.GET.get("include_archived", "").lower() == "true"
    batches = RegistrarBatchService.list_batches(include_archived=include_archived)

    return JsonResponse({
        "success": True,
        "batches": [
            {
                "id": str(b.pk),
                "name": b.name,
                "academic_year": b.academic_year,
                "description": b.description,
                "status": b.status,
                "total_imported": b.total_imported,
                "imported_by": b.imported_by,
                "created_at": b.created_at.isoformat(),
            }
            for b in batches
        ],
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def create_registrar_batch(request):
    """
    POST /api/admin/elections/setup/registrar-batches/create/
    Body: {"name": "...", "academic_year": "...", "description": "..."}
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    try:
        batch = RegistrarBatchService.create_batch(
            name=data.get("name", ""),
            academic_year=data.get("academic_year", ""),
            description=data.get("description", ""),
            imported_by=request.admin_profile.display_name,
        )
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Registrar batch '{batch.name}' created.",
        "batch": {
            "id": str(batch.pk),
            "name": batch.name,
            "academic_year": batch.academic_year,
        },
    }, status=201)


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def import_registrar_batch(request, batch_id):
    """
    POST /api/admin/elections/setup/registrar-batches/<batch_id>/import/
    Content-Type: multipart/form-data with 'csv_file' field.

    Import student data into the registrar batch.
    CSV columns: student_id, full_name, date_of_birth, college, course, year
    """
    try:
        batch = RegistrarImportBatch.objects.get(pk=batch_id)
    except (RegistrarImportBatch.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Batch not found."}, status=404
        )

    if batch.status != RegistrarImportBatch.Status.ACTIVE:
        return JsonResponse(
            {"success": False, "error": "Cannot import into an archived batch."},
            status=400,
        )

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse(
            {"success": False, "error": "csv_file is required."},
            status=400,
        )

    rows, err_resp = _parse_csv_safely(csv_file, max_size_mb=10)
    if err_resp:
        return err_resp

    if "student_id" not in (rows[0].keys() if rows else []):
        return JsonResponse(
            {"success": False, "error": "CSV must have a 'student_id' column."},
            status=400,
        )

    try:
        summary = RegistrarBatchService.import_students_to_batch(batch, rows)
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": (
            f"Import complete: {summary['created']} created, "
            f"{summary['updated']} updated, {summary['skipped']} skipped."
        ),
        "summary": summary,
    })


@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def delete_registrar_batch(request, batch_id):
    """
    POST /api/admin/elections/setup/registrar-batches/<batch_id>/delete/

    Permanently delete a registrar import batch.
    Restricted to EB Head only.
    Blocked if any elections reference this batch (PROTECT FK).
    """
    try:
        batch = RegistrarImportBatch.objects.get(pk=batch_id)
    except (RegistrarImportBatch.DoesNotExist, ValueError, ValidationError):
        return JsonResponse({"success": False, "error": "Batch not found."}, status=404)

    election_count = batch.elections.count()
    if election_count:
        noun = "election" if election_count == 1 else "elections"
        return JsonResponse(
            {
                "success": False,
                "error": (
                    f"Cannot delete — this batch is referenced by "
                    f"{election_count} {noun}. Unlink all elections first."
                ),
            },
            status=400,
        )

    batch_name = batch.name
    batch.delete()
    logger.info(
        "Registrar batch '%s' deleted by %s",
        batch_name,
        request.admin_profile.display_name,
    )
    return JsonResponse({"success": True, "message": f"Batch '{batch_name}' deleted."})


@require_POST
@csrf_protect
@admin_login_required
@role_required(*SETUP_ROLES)
def assign_registrar_batch(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/registrar-batch/assign/
    Body: {"batch_id": "..."}
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    data, err = _parse_json_body(request)
    if err:
        return err

    batch_id = data.get("batch_id")
    if not batch_id:
        return JsonResponse(
            {"success": False, "error": "batch_id is required."},
            status=400,
        )

    try:
        batch = RegistrarImportBatch.objects.get(pk=batch_id)
    except (RegistrarImportBatch.DoesNotExist, ValueError, ValidationError):
        return JsonResponse(
            {"success": False, "error": "Batch not found."}, status=404
        )

    try:
        RegistrarBatchService.assign_batch_to_election(election, batch)
    except VoterRollError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"Batch '{batch.name}' assigned to election.",
    })


# ---------------------------------------------------------------------------
# College management (EB Head / Operator only)
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(*SETUP_ROLES, AdminRole.TALLY_WATCHER)
def list_colleges(request):
    """GET /api/admin/elections/setup/colleges/ — list all colleges."""
    colleges = College.objects.all()
    return JsonResponse({
        "success": True,
        "colleges": [
            {
                "id": str(c.pk),
                "name": c.name,
                "code": c.code,
                "is_active": c.is_active,
            }
            for c in colleges
        ],
    })


@csrf_protect
@require_POST
@admin_login_required
@role_required(*SETUP_ROLES)
def create_college(request):
    """POST /api/admin/elections/setup/colleges/create/ — add a college."""
    data, err = _parse_json_body(request)
    if err:
        return err

    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    if not name:
        return JsonResponse({"success": False, "error": "College name is required."}, status=400)

    if College.objects.filter(name__iexact=name).exists():
        return JsonResponse({"success": False, "error": "A college with that name already exists."}, status=400)

    college = College.objects.create(name=name, code=code, is_active=True)
    return JsonResponse({
        "success": True,
        "college": {"id": str(college.pk), "name": college.name, "code": college.code, "is_active": college.is_active},
    }, status=201)


@csrf_protect
@require_POST
@admin_login_required
@role_required(*SETUP_ROLES)
def update_college(request, college_id):
    """POST /api/admin/elections/setup/colleges/<id>/update/"""
    try:
        college = College.objects.get(pk=college_id)
    except (College.DoesNotExist, ValueError, ValidationError):
        return JsonResponse({"success": False, "error": "College not found."}, status=404)

    data, err = _parse_json_body(request)
    if err:
        return err

    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()
    is_active = data.get("is_active")

    if name and name != college.name:
        if College.objects.filter(name__iexact=name).exclude(pk=college.pk).exists():
            return JsonResponse({"success": False, "error": "A college with that name already exists."}, status=400)
        college.name = name

    if "code" in data:
        college.code = code
    if is_active is not None:
        college.is_active = bool(is_active)

    college.save()
    return JsonResponse({
        "success": True,
        "college": {"id": str(college.pk), "name": college.name, "code": college.code, "is_active": college.is_active},
    })


@csrf_protect
@require_POST
@admin_login_required
@role_required(*SETUP_ROLES)
def delete_college(request, college_id):
    """POST /api/admin/elections/setup/colleges/<id>/delete/"""
    try:
        college = College.objects.get(pk=college_id)
    except (College.DoesNotExist, ValueError, ValidationError):
        return JsonResponse({"success": False, "error": "College not found."}, status=404)

    college.delete()
    return JsonResponse({"success": True, "message": "College deleted."})


# ---------------------------------------------------------------------------
# Position reorder (EB Head only, Draft only)
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def reorder_positions(request, election_id):
    """
    POST /api/admin/elections/setup/<election_id>/positions/reorder/
    Body: {"order": ["position-uuid-1", "position-uuid-2", ...]}

    Reorder positions for an election. Election must be in DRAFT.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status != Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Positions can only be reordered while election is in Draft."},
            status=400,
        )

    data, err = _parse_json_body(request)
    if err:
        return err

    order_list = data.get("order", [])
    if not isinstance(order_list, list) or not order_list:
        return JsonResponse(
            {"success": False, "error": "order must be a non-empty list of position IDs."},
            status=400,
        )

    # Validate all IDs belong to this election
    election_positions = {
        str(p.pk): p
        for p in Position.objects.filter(election=election)
    }

    for pos_id in order_list:
        if str(pos_id) not in election_positions:
            return JsonResponse(
                {"success": False, "error": f"Position '{pos_id}' not found in this election."},
                status=400,
            )

    # Apply new ordering
    for idx, pos_id in enumerate(order_list):
        pos = election_positions[str(pos_id)]
        pos.order = idx + 1
        pos.save(update_fields=["order"])

    return JsonResponse({
        "success": True,
        "message": f"Positions reordered ({len(order_list)} positions).",
    })

