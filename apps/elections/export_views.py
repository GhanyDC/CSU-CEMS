"""
Election export views — CSV exports, turnout summaries, tally reports,
and participation/audit exports.

All exports enforce role-based access and election state validation,
and are audit-logged.
"""
import csv
import io
import logging
from datetime import datetime

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.decorators import admin_login_required, role_required
from apps.accounts.models import AdminRole
from apps.accounts.utils import get_client_ip
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
)
from apps.elections.services import ResultService, TurnoutService
from apps.voting.models import Ballot, BallotSelection

logger = logging.getLogger(__name__)


def _get_election_or_404(election_id):
    """Fetch election by UUID. Returns (election, error_response)."""
    try:
        return Election.objects.get(pk=election_id), None
    except (Election.DoesNotExist, ValueError):
        return None, JsonResponse(
            {"success": False, "error": "Election not found."}, status=404
        )


def _log_export(request, election, export_type):
    """Audit-log an export action."""
    AuditService.log_event(
        student_id_attempted=request.admin_profile.user.username,
        event_type=AuditLog.EventType.EXPORT_GENERATED,
        success=True,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details=(
            f"Export type='{export_type}' for election '{election.name}' "
            f"({election.pk}) by {request.admin_profile.display_name}."
        ),
    )


# ---------------------------------------------------------------------------
# 1. Public Turnout Update Export
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(
    AdminRole.ELECTORAL_BOARD_HEAD,
    AdminRole.ELECTORAL_BOARD_OPERATOR,
    AdminRole.TALLY_WATCHER,
)
def export_turnout_csv(request, election_id):
    """
    GET /api/admin/elections/<election_id>/export/turnout/csv/

    Export turnout data as CSV. Available during Active, Closed, Published.
    Does NOT include per-candidate tallies.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status == Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Turnout export not available for draft elections."},
            status=403,
        )

    turnout = TurnoutService.compute_turnout(election)
    now = timezone.now()

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="turnout_{election.pk}_{now.strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)

    # Header info
    writer.writerow(["Election Turnout Update"])
    writer.writerow(["Election", election.name])
    writer.writerow(["Type", election.get_election_type_display()])
    if election.college:
        writer.writerow(["College", election.college])
    writer.writerow(["Status", election.get_status_display()])
    writer.writerow([f"Unofficial turnout update as of {now.strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])

    # Summary
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Registered/Approved Voters", turnout["total_eligible"]])
    if election.is_hybrid:
        writer.writerow(["Online Ballots Cast", turnout["online_voted"]])
        writer.writerow(["Onsite Turnout Rows", turnout["onsite_voted"]])
        writer.writerow(["Combined Turnout", turnout["combined_voted"]])
        writer.writerow(["Displayed Turnout Count", turnout["total_voted"]])
        writer.writerow(["Online Turnout %", f"{turnout['online_turnout_percentage']}%"])
        writer.writerow(["Onsite Turnout %", f"{turnout['onsite_turnout_percentage']}%"])
        writer.writerow(["Combined Turnout %", f"{turnout['combined_turnout_percentage']}%"])
    else:
        writer.writerow(["Total Ballots Cast", turnout["total_voted"]])
        writer.writerow(["Overall Turnout %", f"{turnout['turnout_percentage']}%"])
    writer.writerow([])

    # Per-college breakdown
    if turnout.get("by_college"):
        if election.is_hybrid:
            writer.writerow([
                "College",
                "Eligible Voters",
                "Online Voted",
                "Onsite Voted",
                "Combined Voted",
            ])
        else:
            writer.writerow(["College", "Eligible Voters"])
        for entry in turnout["by_college"]:
            if election.is_hybrid:
                writer.writerow([
                    entry["college"],
                    entry["eligible"],
                    entry["online_voted"],
                    entry["onsite_voted"],
                    entry["combined_voted"],
                ])
            else:
                writer.writerow([entry["college"], entry["eligible"]])

    _log_export(request, election, "turnout_csv")
    return response


@require_GET
@admin_login_required
@role_required(
    AdminRole.ELECTORAL_BOARD_HEAD,
    AdminRole.ELECTORAL_BOARD_OPERATOR,
    AdminRole.TALLY_WATCHER,
)
def export_turnout_text(request, election_id):
    """
    GET /api/admin/elections/<election_id>/export/turnout/text/

    Export turnout data as plain text summary for copying.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status == Election.Status.DRAFT:
        return JsonResponse(
            {"success": False, "error": "Turnout export not available for draft elections."},
            status=403,
        )

    turnout = TurnoutService.compute_turnout(election)
    now = timezone.now()

    lines = [
        f"UNOFFICIAL TURNOUT UPDATE",
        f"as of {now.strftime('%B %d, %Y %I:%M %p')}",
        f"",
        f"Election: {election.name}",
        f"Type: {election.get_election_type_display()}",
    ]
    if election.college:
        lines.append(f"College: {election.college}")
    lines += [
        f"Status: {election.get_status_display()}",
        f"",
        f"Total Registered Voters: {turnout['total_eligible']:,}",
    ]
    if election.is_hybrid:
        lines += [
            f"Online Ballots Cast: {turnout['online_voted']:,}",
            f"Onsite Turnout Rows: {turnout['onsite_voted']:,}",
            f"Combined Turnout: {turnout['combined_voted']:,}",
            f"Displayed Turnout: {turnout['total_voted']:,}",
            f"Online Turnout: {turnout['online_turnout_percentage']}%",
            f"Onsite Turnout: {turnout['onsite_turnout_percentage']}%",
            f"Combined Turnout: {turnout['combined_turnout_percentage']}%",
        ]
    else:
        lines += [
            f"Total Ballots Cast: {turnout['total_voted']:,}",
            f"Overall Turnout: {turnout['turnout_percentage']}%",
        ]

    if turnout.get("by_college"):
        lines.append("")
        lines.append("Turnout by College:")
        for entry in turnout["by_college"]:
            if election.is_hybrid:
                lines.append(
                    f"  {entry['college']}: {entry['eligible']:,} eligible, "
                    f"{entry['online_voted']:,} online, {entry['onsite_voted']:,} onsite, "
                    f"{entry['combined_voted']:,} combined"
                )
            else:
                lines.append(f"  {entry['college']}: {entry['eligible']:,} eligible")

    response = JsonResponse({
        "success": True,
        "text": "\n".join(lines),
        "generated_at": now.isoformat(),
    })

    _log_export(request, election, "turnout_text")
    return response


# ---------------------------------------------------------------------------
# 2. Internal Canvassing / Tally Export
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(
    AdminRole.ELECTORAL_BOARD_HEAD,
    AdminRole.TALLY_WATCHER,
)
def export_tally_csv(request, election_id):
    """
    GET /api/admin/elections/<election_id>/export/tally/csv/

    Export per-candidate tally as CSV. Available only after Closed.
    EB Head and Tally Watcher only.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status not in (Election.Status.CLOSED, Election.Status.PUBLISHED):
        return JsonResponse(
            {"success": False, "error": "Tally export is only available after the election is closed."},
            status=403,
        )

    results = ResultService.compute_results_with_thresholds(election)
    now = timezone.now()

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="tally_{election.pk}_{now.strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)

    # Header
    writer.writerow(["Internal Canvassing / Tally Report"])
    writer.writerow(["Election", election.name])
    writer.writerow(["Status", election.get_status_display()])
    writer.writerow([f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow([
        "Total Eligible Voters", results["total_eligible"],
    ])
    writer.writerow([
        "Total Ballots Cast", results["total_ballots"],
    ])
    writer.writerow([
        "Overall Turnout", f"{results['turnout_percentage']}%",
    ])
    writer.writerow([])

    # Per-position results
    if election.is_hybrid:
        writer.writerow([
            "Position", "Category", "Candidate", "Party", "College",
            "Online Votes", "Onsite Votes", "Combined Votes", "Displayed Votes",
            "Percentage", "Winner", "Threshold Denominator", "50%+1 Threshold",
        ])
    else:
        writer.writerow([
            "Position", "Category", "Candidate", "Party", "College",
            "Votes", "Percentage", "Winner",
            "Abstain Count", "Position Participation",
            "Threshold Denominator", "50%+1 Threshold",
        ])

    for pos in results["positions"]:
        total_votes = pos["total_votes"]
        for cand in pos.get("results", []):
            votes = cand["votes"]
            pct = round((votes / total_votes * 100) if total_votes > 0 else 0, 2)
            is_winner = pos.get("winner") == cand["candidate"] if isinstance(pos.get("winner"), str) else (
                cand["candidate"] in pos.get("winner", []) if isinstance(pos.get("winner"), list) else False
            )
            if election.is_hybrid:
                writer.writerow([
                    pos["position"],
                    pos["category"],
                    cand["candidate"],
                    cand.get("party", ""),
                    cand.get("college", ""),
                    cand.get("online_votes", 0),
                    cand.get("onsite_votes", 0),
                    cand.get("combined_votes", votes),
                    votes,
                    f"{pct}%",
                    "YES" if is_winner else "",
                    pos.get("threshold_denominator", ""),
                    pos.get("threshold_50_plus_1", ""),
                ])
            else:
                writer.writerow([
                    pos["position"],
                    pos["category"],
                    cand["candidate"],
                    cand.get("party", ""),
                    cand.get("college", ""),
                    votes,
                    f"{pct}%",
                    "YES" if is_winner else "",
                    pos.get("abstain_count", ""),
                    pos.get("position_participation", ""),
                    pos.get("threshold_denominator", ""),
                    pos.get("threshold_50_plus_1", ""),
                ])

    _log_export(request, election, "tally_csv")
    return response


# ---------------------------------------------------------------------------
# 3. Participation / Audit Export
# ---------------------------------------------------------------------------

@require_GET
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def export_participation_csv(request, election_id):
    """
    GET /api/admin/elections/<election_id>/export/participation/csv/

    Export participation data: who voted, who did not vote (by student_id only).
    Available only after Closed. EB Head only.
    Does NOT include vote choices — preserves ballot secrecy.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status not in (Election.Status.CLOSED, Election.Status.PUBLISHED):
        return JsonResponse(
            {"success": False, "error": "Participation export is only available after the election is closed."},
            status=403,
        )

    now = timezone.now()

    # Get all eligible voters
    eligible_voters = (
        EligibleVoter.objects
        .filter(election=election)
        .select_related("student")
        .order_by("student__student_id")
    )

    # Get all ballot hashes to determine who voted
    ballots = Ballot.objects.filter(election=election)
    ballot_hashes = set(ballots.values_list("hashed_student_id", flat=True))
    ballot_timestamps = {
        b.hashed_student_id: b.timestamp
        for b in ballots.only("hashed_student_id", "timestamp")
    }

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="participation_{election.pk}_{now.strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)

    writer.writerow(["Participation Report (Confidential)"])
    writer.writerow(["Election", election.name])
    writer.writerow([f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow([
        "Student ID", "Full Name", "College", "Has Voted", "Vote Timestamp",
    ])

    for ev in eligible_voters:
        student = ev.student
        hashed = Ballot.hash_student_id(student.student_id, str(election.pk))
        voted = hashed in ballot_hashes
        timestamp = ballot_timestamps.get(hashed)
        writer.writerow([
            student.student_id,
            student.full_name,
            ev.college_snapshot,
            "Yes" if voted else "No",
            timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "",
        ])

    _log_export(request, election, "participation_csv")
    return response


@require_GET
@admin_login_required
@role_required(AdminRole.ELECTORAL_BOARD_HEAD)
def export_ballot_audit_csv(request, election_id):
    """
    GET /api/admin/elections/<election_id>/export/ballot-audit/csv/

    Anonymous ballot audit export using ballot IDs and hashed voter identifiers.
    Does NOT include student names or raw student IDs — preserves secrecy.
    Available only after Closed. EB Head only.
    """
    election, err = _get_election_or_404(election_id)
    if err:
        return err

    if election.status not in (Election.Status.CLOSED, Election.Status.PUBLISHED):
        return JsonResponse(
            {"success": False, "error": "Ballot audit export is only available after the election is closed."},
            status=403,
        )

    now = timezone.now()

    ballots = (
        Ballot.objects
        .filter(election=election)
        .prefetch_related("selections__position", "selections__candidate")
        .order_by("timestamp")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="ballot_audit_{election.pk}_{now.strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)

    writer.writerow(["Anonymous Ballot Audit Report"])
    writer.writerow(["Election", election.name])
    writer.writerow([f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow(["NOTE: Hashed voter IDs are anonymized. Student identities are not recoverable."])
    writer.writerow([])
    writer.writerow([
        "Ballot ID", "Hashed Voter ID (truncated)", "Timestamp",
        "Position", "Candidate Selected",
    ])

    for ballot in ballots:
        truncated_hash = ballot.hashed_student_id[:12] + "..."
        selections = ballot.selections.all()
        if selections:
            for sel in selections:
                writer.writerow([
                    str(ballot.pk),
                    truncated_hash,
                    ballot.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    sel.position.title,
                    sel.candidate.full_name,
                ])
        else:
            writer.writerow([
                str(ballot.pk),
                truncated_hash,
                ballot.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "(no selections)",
                "",
            ])

    _log_export(request, election, "ballot_audit_csv")
    return response
