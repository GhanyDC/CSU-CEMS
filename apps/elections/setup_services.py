"""
Election setup services — template-driven creation, candidate management, readiness checks.

These services power the admin election setup workflow (Bundle 03).
They are consumed by admin_views.py API endpoints.
"""
import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    VerificationRecord,
)

logger = logging.getLogger("cems.application")


class ElectionSetupError(Exception):
    """Raised for election setup errors."""


# ---------------------------------------------------------------------------
# Campus election template
# ---------------------------------------------------------------------------

CAMPUS_TEMPLATE = [
    {"title": "President", "category": Position.Category.EXECUTIVE, "max_selections": 1, "order": 1},
    {"title": "Vice President", "category": Position.Category.EXECUTIVE, "max_selections": 1, "order": 2},
    {"title": "Senator", "category": Position.Category.SENATE, "max_selections": 12, "order": 3},
    # College Representatives are generated dynamically (1 per college)
    # Party-List Representative added after college reps
]

COLLEGE_TEMPLATE = [
    {"title": "Governor", "category": Position.Category.COLLEGE_EXECUTIVE, "max_selections": 1, "order": 1},
    {"title": "Vice Governor", "category": Position.Category.COLLEGE_EXECUTIVE, "max_selections": 1, "order": 2},
    {"title": "Board Member", "category": Position.Category.COLLEGE_BOARD, "max_selections": 8, "order": 3},
]


# ---------------------------------------------------------------------------
# Election Setup Service
# ---------------------------------------------------------------------------

class ElectionSetupService:
    """
    Template-driven election creation.

    Campus elections get: President, VP, 12 Senators, 9 College Reps, Party-List Rep.
    College elections get: Governor, Vice Governor, 8 Board Members.
    """

    @staticmethod
    @transaction.atomic
    def create_campus_election(
        name: str,
        start_time: datetime,
        end_time: datetime,
        voting_mode: str = Election.VotingMode.ONLINE,
    ) -> Election:
        """
        Create a campus election with all constitutional positions.

        Returns the created Election instance.
        """
        if not name or not name.strip():
            raise ElectionSetupError("Election name is required.")

        if voting_mode not in {choice[0] for choice in Election.VotingMode.choices}:
            raise ElectionSetupError(f"Invalid voting mode '{voting_mode}'.")

        election = Election.objects.create(
            name=name.strip(),
            election_type=Election.ElectionType.CAMPUS,
            start_time=start_time,
            end_time=end_time,
            status=Election.Status.DRAFT,
            voting_mode=voting_mode,
        )

        # Fixed positions from template
        for tmpl in CAMPUS_TEMPLATE:
            Position.objects.create(election=election, **tmpl)

        # College Representatives — one per official college
        order = 4
        for college in OFFICIAL_COLLEGES:
            short_name = college.replace("College of ", "")
            Position.objects.create(
                election=election,
                title=f"College Representative – {short_name}",
                category=Position.Category.HOUSE_COLLEGE,
                max_selections=1,
                order=order,
            )
            order += 1

        # Party-List Representative
        Position.objects.create(
            election=election,
            title="Party-List Representative",
            category=Position.Category.HOUSE_PARTY,
            max_selections=3,
            order=order,
        )

        logger.info(
            "Campus election created: %s (%s), %d positions",
            election.name, election.pk,
            Position.objects.filter(election=election).count(),
        )
        return election

    @staticmethod
    @transaction.atomic
    def create_college_elections(
        name_prefix: str,
        start_time: datetime,
        end_time: datetime,
        colleges: list[str] | None = None,
        voting_mode: str = Election.VotingMode.ONLINE,
    ) -> list[Election]:
        """
        Bulk-create college elections for all (or specified) official colleges.

        Each college gets a separate Election with Governor, Vice Governor, Board Members.

        Args:
            name_prefix: Base name (e.g. "AY 2025-2026 College Election").
            start_time: Shared start time across all college elections.
            end_time:   Shared end time across all college elections.
            colleges:   Optional subset of OFFICIAL_COLLEGES. Defaults to all 9.

        Returns list of created Election instances.
        """
        if not name_prefix or not name_prefix.strip():
            raise ElectionSetupError("Election name prefix is required.")
        if voting_mode not in {choice[0] for choice in Election.VotingMode.choices}:
            raise ElectionSetupError(f"Invalid voting mode '{voting_mode}'.")

        target_colleges = colleges or list(OFFICIAL_COLLEGES)

        # Validate all college names
        for c in target_colleges:
            if c not in OFFICIAL_COLLEGES:
                raise ElectionSetupError(f"'{c}' is not a recognized official college.")

        elections = []
        for college in target_colleges:
            election = Election.objects.create(
                name=f"{name_prefix.strip()} – {college}",
                election_type=Election.ElectionType.COLLEGE,
                college=college,
                start_time=start_time,
                end_time=end_time,
                status=Election.Status.DRAFT,
                voting_mode=voting_mode,
            )

            for tmpl in COLLEGE_TEMPLATE:
                Position.objects.create(election=election, **tmpl)

            elections.append(election)

        logger.info(
            "College elections created: prefix='%s', count=%d",
            name_prefix.strip(), len(elections),
        )
        return elections

    @staticmethod
    @transaction.atomic
    def update_draft_election_voting_mode(
        election: Election,
        voting_mode: str,
    ) -> Election:
        """Allow changing the voting mode only while the election is still draft."""
        if election.status != Election.Status.DRAFT:
            raise ElectionSetupError("Voting mode can only be changed while the election is in Draft status.")
        if voting_mode not in {choice[0] for choice in Election.VotingMode.choices}:
            raise ElectionSetupError(f"Invalid voting mode '{voting_mode}'.")
        election.voting_mode = voting_mode
        election.save(update_fields=["voting_mode", "updated_at"])
        return election


# ---------------------------------------------------------------------------
# Candidate Management Service
# ---------------------------------------------------------------------------

class CandidateManagementService:
    """
    Manage candidates within draft elections.

    All modifications are blocked once the election leaves DRAFT status.
    """

    @staticmethod
    def _require_draft(election: Election) -> None:
        """Raise if the election is not in DRAFT status."""
        if election.status != Election.Status.DRAFT:
            raise ElectionSetupError(
                "Candidates can only be modified while the election is in Draft status."
            )

    @staticmethod
    @transaction.atomic
    def add_candidate(
        position: Position,
        full_name: str,
        party: str = "",
        college: str = "",
    ) -> Candidate:
        """Add a candidate to a position. Election must be in DRAFT."""
        CandidateManagementService._require_draft(position.election)

        if not full_name or not full_name.strip():
            raise ElectionSetupError("Candidate name is required.")

        # Check uniqueness
        if Candidate.objects.filter(position=position, full_name=full_name.strip()).exists():
            raise ElectionSetupError(
                f"A candidate named '{full_name.strip()}' already exists for this position."
            )

        candidate = Candidate.objects.create(
            position=position,
            full_name=full_name.strip(),
            party=party.strip() if party else "",
            college=college.strip() if college else "",
            is_active=True,
        )

        logger.info(
            "Candidate added: %s for %s in %s",
            candidate.full_name, position.title, position.election.name,
        )
        return candidate

    @staticmethod
    @transaction.atomic
    def update_candidate(
        candidate: Candidate,
        full_name: str | None = None,
        party: str | None = None,
        college: str | None = None,
        is_active: bool | None = None,
    ) -> Candidate:
        """Update a candidate's details. Election must be in DRAFT."""
        CandidateManagementService._require_draft(candidate.position.election)

        update_fields = ["updated_at"]

        if full_name is not None:
            if not full_name.strip():
                raise ElectionSetupError("Candidate name cannot be empty.")
            # Check uniqueness against other candidates in same position
            if (
                Candidate.objects.filter(
                    position=candidate.position,
                    full_name=full_name.strip(),
                )
                .exclude(pk=candidate.pk)
                .exists()
            ):
                raise ElectionSetupError(
                    f"A candidate named '{full_name.strip()}' already exists for this position."
                )
            candidate.full_name = full_name.strip()
            update_fields.append("full_name")

        if party is not None:
            candidate.party = party.strip()
            update_fields.append("party")

        if college is not None:
            candidate.college = college.strip()
            update_fields.append("college")

        if is_active is not None:
            candidate.is_active = is_active
            update_fields.append("is_active")

        candidate.save(update_fields=update_fields)

        logger.info(
            "Candidate updated: %s (%s)", candidate.full_name, candidate.pk,
        )
        return candidate


# ---------------------------------------------------------------------------
# Readiness Service
# ---------------------------------------------------------------------------

class ReadinessService:
    """
    Checks whether an election is ready to be started.

    Returns a structured checklist with pass/fail for each requirement.
    """

    @staticmethod
    def check_readiness(election: Election) -> dict:
        """
        Return a readiness report for the given election.

        Returns:
            {
                "election_id": "...",
                "election_name": "...",
                "election_type": "campus" | "college",
                "status": "draft" | ...,
                "checks": [
                    {"name": "...", "passed": bool, "detail": "..."},
                ],
                "ready": bool,
                "blocking_issues": ["..."],
            }
        """
        checks = []
        blocking = []

        # 1. Schedule set
        has_schedule = (
            election.start_time is not None
            and election.end_time is not None
            and election.end_time > election.start_time
        )
        checks.append({
            "name": "Schedule configured",
            "passed": has_schedule,
            "detail": (
                f"{election.start_time.strftime('%Y-%m-%d %H:%M')} to "
                f"{election.end_time.strftime('%Y-%m-%d %H:%M')}"
                if has_schedule else "Schedule not set"
            ),
        })
        if not has_schedule:
            blocking.append("Schedule not properly configured.")

        # 2. Positions created
        position_count = Position.objects.filter(election=election).count()
        checks.append({
            "name": "Positions created",
            "passed": position_count > 0,
            "detail": f"{position_count} position(s)",
        })
        if position_count == 0:
            blocking.append("No positions created.")

        # 3. All positions have at least one active candidate
        positions = Position.objects.filter(election=election)
        positions_without_candidates = []
        for pos in positions:
            active_count = Candidate.objects.filter(
                position=pos, is_active=True,
            ).count()
            if active_count == 0:
                positions_without_candidates.append(pos.title)

        all_have_candidates = len(positions_without_candidates) == 0 and position_count > 0
        if positions_without_candidates:
            detail = f"{len(positions_without_candidates)} position(s) missing candidates: {', '.join(positions_without_candidates[:5])}"
            if len(positions_without_candidates) > 5:
                detail += f" (+{len(positions_without_candidates) - 5} more)"
        elif position_count > 0:
            total_candidates = Candidate.objects.filter(
                position__election=election, is_active=True,
            ).count()
            detail = f"All {position_count} positions have candidates ({total_candidates} total)"
        else:
            detail = "No positions to check"
        checks.append({
            "name": "All positions have candidates",
            "passed": all_have_candidates,
            "detail": detail,
        })
        if not all_have_candidates and position_count > 0:
            blocking.append(
                f"{len(positions_without_candidates)} position(s) have no active candidates."
            )

        # 4. Verification records imported
        import_count = VerificationRecord.objects.filter(election=election).count()
        checks.append({
            "name": "Verification records imported",
            "passed": import_count > 0,
            "detail": f"{import_count} record(s) imported",
        })
        if import_count == 0:
            blocking.append("No verification records imported.")

        # 5. Voter roll generated
        voter_count = EligibleVoter.objects.filter(election=election).count()
        checks.append({
            "name": "Voter roll generated",
            "passed": voter_count > 0,
            "detail": f"{voter_count} eligible voter(s)",
        })
        if voter_count == 0:
            blocking.append("Voter roll has not been generated.")

        # 6. Voter roll finalized
        checks.append({
            "name": "Voter roll finalized",
            "passed": election.is_voter_roll_finalized,
            "detail": (
                f"Finalized by {election.voter_roll_finalized_by} "
                f"at {election.voter_roll_finalized_at.strftime('%Y-%m-%d %H:%M')}"
                if election.is_voter_roll_finalized
                else "Not finalized"
            ),
        })
        if not election.is_voter_roll_finalized:
            blocking.append("Voter roll has not been finalized.")

        # 7. Election is in DRAFT
        is_draft = election.status == Election.Status.DRAFT
        checks.append({
            "name": "Election is in Draft",
            "passed": is_draft,
            "detail": f"Current status: {election.get_status_display()}",
        })
        if not is_draft:
            blocking.append(f"Election is not in Draft (currently {election.get_status_display()}).")

        ready = len(blocking) == 0
        return {
            "election_id": str(election.pk),
            "election_name": election.name,
            "election_type": election.election_type,
            "status": election.status,
            "checks": checks,
            "ready": ready,
            "blocking_issues": blocking,
        }


# ---------------------------------------------------------------------------
# Position Management Service (EB Head only)
# ---------------------------------------------------------------------------

class PositionManagementService:
    """
    Add, update, and delete positions within a draft election.

    All modifications are blocked once the election leaves DRAFT status.
    Only the Electoral Board Head may invoke these methods.
    """

    _VALID_CATEGORIES = {c.value for c in Position.Category}

    @staticmethod
    def _require_draft(election: Election) -> None:
        if election.status != Election.Status.DRAFT:
            raise ElectionSetupError(
                "Positions can only be modified while the election is in Draft status."
            )

    @staticmethod
    @transaction.atomic
    def add_position(
        election: Election,
        title: str,
        category: str,
        max_selections: int = 1,
        order: int = 0,
    ) -> "Position":
        """Create a new position for the election. Election must be in DRAFT."""
        PositionManagementService._require_draft(election)

        title = (title or "").strip()
        if not title:
            raise ElectionSetupError("Position title is required.")

        if category not in PositionManagementService._VALID_CATEGORIES:
            raise ElectionSetupError(f"Invalid category '{category}'.")

        if not isinstance(max_selections, int) or max_selections < 1:
            raise ElectionSetupError("max_selections must be a positive integer.")

        if Position.objects.filter(election=election, title=title).exists():
            raise ElectionSetupError(
                f"A position titled '{title}' already exists in this election."
            )

        position = Position.objects.create(
            election=election,
            title=title,
            category=category,
            max_selections=max_selections,
            order=order,
        )
        logger.info(
            "Position added: '%s' (%s) in election %s",
            position.title, position.pk, election.name,
        )
        return position

    @staticmethod
    @transaction.atomic
    def update_position(
        position: "Position",
        title: str | None = None,
        category: str | None = None,
        max_selections: int | None = None,
        order: int | None = None,
    ) -> "Position":
        """Update a position's fields. Election must be in DRAFT."""
        PositionManagementService._require_draft(position.election)

        update_fields: list[str] = []

        if title is not None:
            title = title.strip()
            if not title:
                raise ElectionSetupError("Position title cannot be empty.")
            if (
                Position.objects.filter(election=position.election, title=title)
                .exclude(pk=position.pk)
                .exists()
            ):
                raise ElectionSetupError(
                    f"A position titled '{title}' already exists in this election."
                )
            position.title = title
            update_fields.append("title")

        if category is not None:
            if category not in PositionManagementService._VALID_CATEGORIES:
                raise ElectionSetupError(f"Invalid category '{category}'.")
            position.category = category
            update_fields.append("category")

        if max_selections is not None:
            if not isinstance(max_selections, int) or max_selections < 1:
                raise ElectionSetupError("max_selections must be a positive integer.")
            position.max_selections = max_selections
            update_fields.append("max_selections")

        if order is not None:
            position.order = order
            update_fields.append("order")

        if update_fields:
            position.save(update_fields=update_fields)
            logger.info("Position updated: '%s' (%s)", position.title, position.pk)
        return position

    @staticmethod
    @transaction.atomic
    def delete_position(position: "Position") -> None:
        """Hard-delete a position and its candidates. Election must be in DRAFT."""
        PositionManagementService._require_draft(position.election)
        name = position.title
        pk = position.pk
        position.delete()
        logger.info("Position deleted: '%s' (%s)", name, pk)
