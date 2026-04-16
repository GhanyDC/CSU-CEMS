"""
Election services — lifecycle management, result computation, and voter roll management.
"""
import logging

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.hybrid_services import HybridElectionService
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    RegistrarImportBatch,
    VerificationRecord,
)
from apps.voting.models import Ballot, BallotSelection

logger = logging.getLogger("cems.application")


class InvalidTransitionError(Exception):
    """Raised when an election status transition is not allowed."""


class ElectionNotReadyError(Exception):
    """Raised when an election cannot be published (e.g. not closed)."""


# ---------------------------------------------------------------------------
# Election Lifecycle
# ---------------------------------------------------------------------------

class ElectionLifecycleService:
    """
    Manages the election state machine:
        DRAFT → ACTIVE → CLOSED → PUBLISHED

    Each transition is validated and audit-logged.
    """

    # Valid transitions: current_status → next_status
    _TRANSITIONS = {
        Election.Status.DRAFT: Election.Status.ACTIVE,
        Election.Status.ACTIVE: Election.Status.CLOSED,
        Election.Status.CLOSED: Election.Status.PUBLISHED,
    }

    _AUDIT_EVENTS = {
        Election.Status.ACTIVE: AuditLog.EventType.ELECTION_STARTED,
        Election.Status.CLOSED: AuditLog.EventType.ELECTION_CLOSED,
        Election.Status.PUBLISHED: AuditLog.EventType.RESULTS_PUBLISHED,
    }

    @classmethod
    @transaction.atomic
    def transition(
        cls,
        election: Election,
        target_status: str,
        *,
        performed_by: str = "system",
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> Election:
        """
        Advance an election to the next valid status.

        Uses select_for_update to prevent concurrent transitions.

        Args:
            election:       The Election instance to transition.
            target_status:  The desired new status value.
            performed_by:   Identifier for the actor (admin student_id or "system").
            ip_address:     Optional client IP for audit.
            user_agent:     Optional UA for audit.

        Returns:
            The updated Election instance.

        Raises:
            InvalidTransitionError: If the transition is not valid.
        """
        # Lock the election row to prevent race conditions
        election = Election.objects.select_for_update().get(pk=election.pk)

        allowed_next = cls._TRANSITIONS.get(election.status)

        if allowed_next is None or allowed_next != target_status:
            raise InvalidTransitionError(
                f"Cannot transition election from '{election.get_status_display()}' "
                f"to '{target_status}'. "
                f"Allowed next status: {allowed_next or 'none (terminal state)'}."
            )

        old_status = election.status
        election.status = target_status
        election.save(update_fields=["status", "updated_at"])

        # Audit log
        event_type = cls._AUDIT_EVENTS.get(target_status)
        if event_type:
            AuditService.log_event(
                student_id_attempted=performed_by,
                event_type=event_type,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
                details=(
                    f"Election '{election.name}' ({election.pk}) "
                    f"transitioned from {old_status} to {target_status}."
                ),
            )

        logger.info(
            "Election lifecycle transition: election_id=%s, %s → %s, by=%s",
            election.pk, old_status, target_status, performed_by,
        )
        return election

    @classmethod
    def start_election(cls, election: Election, **kwargs) -> Election:
        # Voter roll must be finalized before starting (only check for valid transition)
        fresh = Election.objects.get(pk=election.pk)
        if fresh.status == Election.Status.DRAFT and not fresh.is_voter_roll_finalized:
            raise ElectionNotReadyError(
                "Cannot start election: voter roll has not been finalized."
            )
        return cls.transition(election, Election.Status.ACTIVE, **kwargs)

    @classmethod
    def close_election(cls, election: Election, **kwargs) -> Election:
        return cls.transition(election, Election.Status.CLOSED, **kwargs)

    @classmethod
    def publish_results(cls, election: Election, **kwargs) -> Election:
        fresh = Election.objects.get(pk=election.pk)
        if fresh.is_hybrid and not HybridElectionService.has_required_imports(fresh):
            raise ElectionNotReadyError(
                "Cannot publish hybrid election until both onsite turnout and onsite tally imports are completed."
            )
        return cls.transition(election, Election.Status.PUBLISHED, **kwargs)


# ---------------------------------------------------------------------------
# Result Computation
# ---------------------------------------------------------------------------

class ResultService:
    """
    Computes election results from BallotSelection records.

    Rules by position category:
    - EXECUTIVE:     Majority required (50% + 1). If no majority → "no_majority".
    - SENATE:        Top N candidates win (N = position.max_selections).
    - HOUSE_COLLEGE: Plurality (highest votes wins).
    - HOUSE_PARTY:   Plurality (highest votes wins).
    """

    @staticmethod
    def compute_results(election: Election) -> dict:
        positions = Position.objects.filter(election=election).order_by("order", "title")
        turnout_context = HybridElectionService.compute_turnout_breakdown(election)
        result_context = HybridElectionService.get_position_result_context(election)
        total_eligible = turnout_context["total_eligible"]
        has_official_onsite_results = result_context["has_official_onsite_results"]
        total_ballots = (
            turnout_context["combined_voted"]
            if has_official_onsite_results
            else turnout_context["online_voted"]
        )

        eligible_by_college = {}
        if election.is_campus:
            eligible_by_college = {
                row["college_snapshot"]: row["count"]
                for row in (
                    EligibleVoter.objects
                    .filter(election=election)
                    .values("college_snapshot")
                    .annotate(count=Count("id"))
                )
            }

        positions_data = [
            ResultService._compute_position_result(
                position,
                total_ballots_in_election=total_ballots,
                total_eligible=total_eligible,
                eligible_by_college=eligible_by_college,
                result_context=result_context,
            )
            for position in positions
        ]

        return {
            "election_id": str(election.pk),
            "election_name": election.name,
            "voting_mode": election.voting_mode,
            "counting_mode": (
                "combined_official"
                if has_official_onsite_results
                else ("online_partial" if election.is_hybrid else "online_only")
            ),
            "total_eligible": total_eligible,
            "total_ballots": total_ballots,
            "online_ballots": turnout_context["online_voted"],
            "onsite_ballots": turnout_context["onsite_voted"],
            "combined_ballots": turnout_context["combined_voted"],
            "turnout_percentage": round(
                (total_ballots / total_eligible * 100) if total_eligible > 0 else 0, 2
            ),
            "positions": positions_data,
            "hybrid": (
                HybridElectionService.build_hybrid_summary(election)
                if election.is_hybrid
                else None
            ),
        }

    @staticmethod
    def _compute_position_result(
        position: Position,
        *,
        total_ballots_in_election: int,
        total_eligible: int,
        eligible_by_college: dict[str, int] | None = None,
        result_context: dict | None = None,
    ) -> dict:
        """Compute results for a single position, including source-specific tallies."""
        context = result_context or {}
        online_vote_counts = context.get("online_vote_counts", {})
        onsite_vote_counts = context.get("onsite_vote_counts", {})
        online_position_participation = context.get("online_position_participation", {})
        has_official_onsite_results = context.get("has_official_onsite_results", False)

        candidates = list(
            Candidate.objects
            .filter(position=position, is_active=True)
            .order_by("full_name")
        )
        results = []
        for candidate in candidates:
            online_votes = int(online_vote_counts.get(str(candidate.pk), 0) or 0)
            onsite_votes = int(onsite_vote_counts.get(str(candidate.pk), 0) or 0)
            combined_votes = online_votes + onsite_votes
            display_votes = combined_votes if has_official_onsite_results else online_votes
            results.append(
                {
                    "candidate_id": str(candidate.pk),
                    "candidate": candidate.full_name,
                    "full_name": candidate.full_name,
                    "party": candidate.party,
                    "college": candidate.college or "",
                    "photo_url": candidate.photo.url if candidate.photo else None,
                    "votes": display_votes,
                    "online_votes": online_votes,
                    "onsite_votes": onsite_votes,
                    "combined_votes": combined_votes,
                }
            )

        results.sort(key=lambda row: (-row["votes"], row["candidate"].lower()))

        total_votes = sum(r["votes"] for r in results)
        online_total_votes = sum(r["online_votes"] for r in results)
        onsite_total_votes = sum(r["onsite_votes"] for r in results)
        combined_total_votes = sum(r["combined_votes"] for r in results)
        candidate_count = len(results)
        single_candidate_threshold_applies = candidate_count == 1

        threshold_denominator, threshold_scope = ResultService._get_position_threshold_context(
            position,
            results,
            total_eligible=total_eligible,
            eligible_by_college=eligible_by_college or {},
        )
        threshold_50_plus_1 = (
            (threshold_denominator // 2) + 1 if threshold_denominator > 0 else 0
        )

        # Determine winner(s) based on category
        winner, status = ResultService._determine_winner(
            position,
            results,
            total_votes,
            single_candidate_threshold_applies=single_candidate_threshold_applies,
            threshold_50_plus_1=threshold_50_plus_1,
        )

        ballots_with_selection = int(
            online_position_participation.get(str(position.pk), 0) or 0
        )
        if has_official_onsite_results:
            abstain_count = None
            position_participation = None
            participation_note = (
                "Position-level abstain counts are hidden once onsite aggregate tallies "
                "are combined because per-position onsite abstentions are not imported."
            )
        else:
            abstain_count = max(0, total_ballots_in_election - ballots_with_selection)
            position_participation = ballots_with_selection
            participation_note = ""

        return {
            "position_id": str(position.pk),
            "position": position.title,
            "category": position.category,
            "total_votes": total_votes,
            "online_total_votes": online_total_votes,
            "onsite_total_votes": onsite_total_votes,
            "combined_total_votes": combined_total_votes,
            "max_selections": position.max_selections,
            "winner": winner,
            "status": status,
            "candidate_count": candidate_count,
            "single_candidate_threshold_applies": single_candidate_threshold_applies,
            "results": results,
            "abstain_count": abstain_count,
            "position_participation": position_participation,
            "total_ballots": total_ballots_in_election,
            "counting_mode": (
                "combined_official" if has_official_onsite_results else "online_only"
            ),
            "participation_note": participation_note,
            "threshold_denominator": threshold_denominator,
            "threshold_50_plus_1": threshold_50_plus_1,
            "threshold_scope": threshold_scope,
        }

    @staticmethod
    def _determine_winner(
        position: Position,
        results: list[dict],
        total_votes: int,
        *,
        single_candidate_threshold_applies: bool = False,
        threshold_50_plus_1: int = 0,
    ) -> tuple[str | list[str] | None, str]:
        """
        Apply the appropriate winning rule for this position's category.

        Returns:
            (winner, status) where:
            - winner is a name string, list of names, or None
            - status is "won", "no_majority", "threshold_not_met", or "no_votes"
        """
        if not results:
            return None, "no_votes"

        if single_candidate_threshold_applies:
            return ResultService._single_candidate_threshold_rule(
                results[0],
                threshold_50_plus_1,
            )

        if total_votes == 0:
            return None, "no_votes"

        category = position.category

        if category in (
            Position.Category.EXECUTIVE,
            Position.Category.COLLEGE_EXECUTIVE,
        ):
            return ResultService._executive_rule(results, total_votes)

        if category in (
            Position.Category.SENATE,
            Position.Category.COLLEGE_BOARD,
        ):
            return ResultService._multi_seat_rule(results, position.max_selections)

        # HOUSE_COLLEGE and HOUSE_PARTY: single-seat plurality
        return ResultService._plurality_rule(results)

    @staticmethod
    def _executive_rule(
        results: list[dict], total_votes: int,
    ) -> tuple[str | None, str]:
        """
        Executive positions require an absolute majority (50% + 1).
        """
        majority_threshold = (total_votes // 2) + 1

        if results and results[0]["votes"] >= majority_threshold:
            return results[0]["candidate"], "won"

        return None, "no_majority"

    @staticmethod
    def _single_candidate_threshold_rule(
        result: dict,
        threshold_50_plus_1: int,
    ) -> tuple[str | None, str]:
        """
        Any position with exactly one active candidate requires 50% + 1 of the
        registered voters in that position's scope.
        """
        if result["votes"] <= 0:
            return None, "no_votes"

        if threshold_50_plus_1 > 0 and result["votes"] >= threshold_50_plus_1:
            return result["candidate"], "won"

        return None, "threshold_not_met"

    @staticmethod
    def _multi_seat_rule(
        results: list[dict], seats: int,
    ) -> tuple[list[str], str]:
        """
        Multi-seat positions (Senate): top N candidates by vote count win.
        """
        winners = [r["candidate"] for r in results[:seats] if r["votes"] > 0]
        return winners, "won"

    @staticmethod
    def _plurality_rule(results: list[dict]) -> tuple[str | None, str]:
        """
        Single-seat plurality: candidate with most votes wins.
        """
        if results and results[0]["votes"] > 0:
            return results[0]["candidate"], "won"
        return None, "no_votes"

    @staticmethod
    def _get_position_threshold_context(
        position: Position,
        results: list[dict],
        *,
        total_eligible: int,
        eligible_by_college: dict[str, int],
    ) -> tuple[int, str]:
        """
        Return the denominator and scope label for the position's 50%+1 rule.
        """
        if position.category == Position.Category.HOUSE_COLLEGE and position.election.is_campus:
            represented_college = ResultService._resolve_house_college_scope(
                position,
                results,
            )
            return eligible_by_college.get(represented_college, 0), represented_college

        if position.election.is_college:
            return total_eligible, position.election.college or "college election"

        return total_eligible, "campus election"

    @staticmethod
    def _resolve_house_college_scope(position: Position, results: list[dict]) -> str:
        """
        Resolve which college voter roll should be used for a campus college-rep seat.
        """
        candidate_colleges = {
            (row.get("college") or "").strip()
            for row in results
            if (row.get("college") or "").strip()
        }
        if len(candidate_colleges) == 1:
            return next(iter(candidate_colleges))

        active_candidate_colleges = {
            college.strip()
            for college in Candidate.objects.filter(position=position, is_active=True)
            .exclude(college__isnull=True)
            .exclude(college="")
            .values_list("college", flat=True)
            if college and college.strip()
        }
        if len(active_candidate_colleges) == 1:
            return next(iter(active_candidate_colleges))

        title = (position.title or "").strip()
        short_name = ""
        for separator in (" - ", " – ", "â€“", "—"):
            if separator in title:
                short_name = title.split(separator, 1)[1].strip()
                break

        if not short_name and title.lower().startswith("college representative"):
            short_name = title[len("College Representative"):].strip(" -–â€“—")

        short_name_lower = short_name.lower()
        for official_college in OFFICIAL_COLLEGES:
            official_lower = official_college.lower()
            short_official = official_college.replace("College of ", "").strip().lower()
            if short_name_lower in {official_lower, short_official}:
                return official_college

        return short_name

    @staticmethod
    def compute_results_with_thresholds(election: Election) -> dict:
        return ResultService.compute_results(election)


# ---------------------------------------------------------------------------
# Turnout Service
# ---------------------------------------------------------------------------

class TurnoutService:
    """
    Provides turnout/progress data for monitoring during active elections.
    Does NOT expose per-candidate tallies.
    """

    @staticmethod
    def compute_turnout(election: Election) -> dict:
        turnout = HybridElectionService.compute_turnout_breakdown(election)
        total_eligible = turnout["total_eligible"]
        total_voted = turnout["official_total_voted"]

        return {
            "election_id": str(election.pk),
            "election_name": election.name,
            "election_type": election.election_type,
            "voting_mode": election.voting_mode,
            "status": election.status,
            "generated_at": timezone.now().isoformat(),
            "total_eligible": total_eligible,
            "total_voted": total_voted,
            "online_voted": turnout["online_voted"],
            "onsite_voted": turnout["onsite_voted"],
            "combined_voted": turnout["combined_voted"],
            "has_official_onsite_turnout": turnout["has_official_onsite_turnout"],
            "turnout_percentage": round(
                (total_voted / total_eligible * 100) if total_eligible > 0 else 0, 2
            ),
            "online_turnout_percentage": round(
                (turnout["online_voted"] / total_eligible * 100) if total_eligible > 0 else 0,
                2,
            ),
            "onsite_turnout_percentage": round(
                (turnout["onsite_voted"] / total_eligible * 100) if total_eligible > 0 else 0,
                2,
            ),
            "combined_turnout_percentage": round(
                (turnout["combined_voted"] / total_eligible * 100) if total_eligible > 0 else 0,
                2,
            ),
            "by_college": turnout["by_college"],
        }


# ---------------------------------------------------------------------------
# Voter Roll Management
# ---------------------------------------------------------------------------

class VoterRollError(Exception):
    """Raised for voter-roll pipeline errors."""


class VoterRollService:
    """
    Manages the per-election voter roll lifecycle:
      1. Import verification form CSV rows
      2. Match against the registrar (Student table)
      3. Generate EligibleVoter records from matched entries
      4. Finalize the voter roll (locks it)
    """

    @staticmethod
    @transaction.atomic
    def import_verification(
        election: Election,
        rows: list[dict],
    ) -> dict:
        """
        Import verification form rows for an election.

        Args:
            election: The election to import verification records for.
            rows: List of dicts with keys: student_id, full_name (optional), college (optional).

        Returns:
            Summary dict: {created, skipped_duplicate, matched, unmatched}.
        """
        from apps.accounts.models import Student

        if election.is_voter_roll_finalized:
            raise VoterRollError("Cannot import: voter roll is already finalized.")

        # Pre-load existing student IDs from the registrar for fast lookup
        student_map = {
            s.student_id: s
            for s in Student.objects.all().only("pk", "student_id")
        }

        # Pre-load already-imported student_id_input values for this election
        existing_ids = set(
            VerificationRecord.objects
            .filter(election=election)
            .values_list("student_id_input", flat=True)
        )

        created = 0
        skipped_duplicate = 0
        matched = 0
        unmatched = 0

        records_to_create = []
        for row in rows:
            sid = row.get("student_id", "").strip()
            if not sid:
                continue

            if sid in existing_ids:
                skipped_duplicate += 1
                continue

            existing_ids.add(sid)
            student = student_map.get(sid)

            if student:
                status = VerificationRecord.MatchStatus.MATCHED
                matched += 1
            else:
                status = VerificationRecord.MatchStatus.UNMATCHED
                unmatched += 1

            records_to_create.append(VerificationRecord(
                election=election,
                student_id_input=sid,
                full_name_input=row.get("full_name", "").strip(),
                college_input=row.get("college", "").strip(),
                matched_student=student,
                status=status,
            ))
            created += 1

        if records_to_create:
            VerificationRecord.objects.bulk_create(records_to_create)

        logger.info(
            "Verification import: election=%s, created=%d, skipped=%d, matched=%d, unmatched=%d",
            election.pk, created, skipped_duplicate, matched, unmatched,
        )

        return {
            "created": created,
            "skipped_duplicate": skipped_duplicate,
            "matched": matched,
            "unmatched": unmatched,
        }

    @staticmethod
    def get_match_summary(election: Election) -> dict:
        """Return counts of verification records by status."""
        counts = (
            VerificationRecord.objects
            .filter(election=election)
            .values("status")
            .annotate(count=Count("id"))
        )
        summary = {
            "total": 0,
            "matched": 0,
            "unmatched": 0,
            "duplicate": 0,
            "pending": 0,
        }
        for row in counts:
            summary[row["status"]] = row["count"]
            summary["total"] += row["count"]
        return summary

    @staticmethod
    def get_unmatched_records(election: Election):
        """Return queryset of unmatched verification records."""
        return VerificationRecord.objects.filter(
            election=election,
            status=VerificationRecord.MatchStatus.UNMATCHED,
        )

    @staticmethod
    @transaction.atomic
    def generate_voter_roll(election: Election) -> int:
        """
        Create EligibleVoter records from MATCHED verification records.

        For college elections, only students whose college matches the
        election's college are included.

        Returns the number of EligibleVoter records created.
        """
        if election.is_voter_roll_finalized:
            raise VoterRollError("Cannot generate: voter roll is already finalized.")

        matched_records = VerificationRecord.objects.filter(
            election=election,
            status=VerificationRecord.MatchStatus.MATCHED,
            matched_student__isnull=False,
        ).select_related("matched_student")

        # Filter already-enrolled voters
        existing_student_ids = set(
            EligibleVoter.objects
            .filter(election=election)
            .values_list("student_id", flat=True)
        )

        voters_to_create = []
        for record in matched_records:
            student = record.matched_student
            if student.pk in existing_student_ids:
                continue

            # For college elections, only include students from the matching college
            if election.is_college and student.college != election.college:
                continue

            voters_to_create.append(EligibleVoter(
                election=election,
                student=student,
                college_snapshot=student.college or "",
            ))
            existing_student_ids.add(student.pk)

        if voters_to_create:
            EligibleVoter.objects.bulk_create(voters_to_create)

        logger.info(
            "Voter roll generated: election=%s, created=%d",
            election.pk, len(voters_to_create),
        )
        return len(voters_to_create)

    @staticmethod
    @transaction.atomic
    def finalize_voter_roll(
        election: Election,
        finalized_by: str,
    ) -> None:
        """
        Lock the voter roll for an election.

        After finalization, no more EligibleVoter records can be added or removed.
        """
        election = Election.objects.select_for_update().get(pk=election.pk)

        if election.is_voter_roll_finalized:
            raise VoterRollError("Voter roll is already finalized.")

        if not EligibleVoter.objects.filter(election=election).exists():
            raise VoterRollError("Cannot finalize an empty voter roll.")

        election.voter_roll_finalized_at = timezone.now()
        election.voter_roll_finalized_by = finalized_by
        election.save(update_fields=[
            "voter_roll_finalized_at",
            "voter_roll_finalized_by",
            "updated_at",
        ])

        logger.info(
            "Voter roll finalized: election=%s, by=%s, count=%d",
            election.pk, finalized_by,
            EligibleVoter.objects.filter(election=election).count(),
        )

    @staticmethod
    def get_approved_count(election: Election) -> int:
        """Return the total number of eligible voters for an election."""
        return EligibleVoter.objects.filter(election=election).count()

    @staticmethod
    def get_approved_count_by_college(election: Election) -> dict[str, int]:
        """Return eligible voter counts grouped by college_snapshot."""
        counts = (
            EligibleVoter.objects
            .filter(election=election)
            .values("college_snapshot")
            .annotate(count=Count("id"))
        )
        return {row["college_snapshot"]: row["count"] for row in counts}


# ---------------------------------------------------------------------------
# Registrar Batch Service
# ---------------------------------------------------------------------------

class RegistrarBatchService:
    """
    Manages system-level registrar import batches.

    A registrar batch represents a school-year student roster dataset.
    Elections reference a batch for voter roll matching.
    """

    @staticmethod
    @transaction.atomic
    def create_batch(
        name: str,
        academic_year: str = "",
        description: str = "",
        imported_by: str = "",
    ) -> RegistrarImportBatch:
        """Create a new registrar import batch."""
        if not name or not name.strip():
            raise VoterRollError("Batch name is required.")

        batch = RegistrarImportBatch.objects.create(
            name=name.strip(),
            academic_year=academic_year.strip(),
            description=description.strip(),
            imported_by=imported_by,
        )
        logger.info("Registrar batch created: %s (%s)", batch.name, batch.pk)
        return batch

    @staticmethod
    @transaction.atomic
    def import_students_to_batch(
        batch: RegistrarImportBatch,
        rows: list[dict],
    ) -> dict:
        """
        Import student records from CSV rows into the Student table,
        tagged with this batch.

        Args:
            batch: The RegistrarImportBatch to associate with.
            rows: List of dicts with keys: student_id, full_name, date_of_birth, college, course, year.

        Returns:
            Summary dict: {created, updated, skipped, errors}.
        """
        from apps.accounts.models import Student
        from datetime import date

        created = 0
        updated = 0
        skipped = 0
        errors = []

        for i, row in enumerate(rows):
            sid = row.get("student_id", "").strip()
            if not sid:
                skipped += 1
                continue

            full_name = row.get("full_name", "").strip()
            dob_raw = row.get("date_of_birth", "").strip()
            college = row.get("college", "").strip()
            course = row.get("course", "").strip()
            year_raw = row.get("year", "1").strip()

            if not full_name:
                errors.append(f"Row {i+1}: missing full_name for {sid}")
                continue

            try:
                dob = date.fromisoformat(dob_raw) if dob_raw else date(2000, 1, 1)
            except (ValueError, TypeError):
                errors.append(f"Row {i+1}: invalid date_of_birth for {sid}")
                continue

            try:
                year_val = int(year_raw) if year_raw else 1
            except (ValueError, TypeError):
                year_val = 1

            student, was_created = Student.objects.update_or_create(
                student_id=sid,
                defaults={
                    "full_name": full_name,
                    "date_of_birth": dob,
                    "college": college,
                    "course": course,
                    "year": year_val,
                },
            )

            if was_created:
                created += 1
            else:
                updated += 1

        batch.total_imported = created + updated
        batch.save(update_fields=["total_imported", "updated_at"])

        logger.info(
            "Registrar batch import: batch=%s, created=%d, updated=%d, skipped=%d, errors=%d",
            batch.pk, created, updated, skipped, len(errors),
        )

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:20],  # Limit error details
        }

    @staticmethod
    def list_batches(include_archived: bool = False):
        """Return queryset of registrar import batches."""
        qs = RegistrarImportBatch.objects.all()
        if not include_archived:
            qs = qs.filter(status=RegistrarImportBatch.Status.ACTIVE)
        return qs.order_by("-created_at")

    @staticmethod
    @transaction.atomic
    def archive_batch(batch: RegistrarImportBatch) -> None:
        """Archive a batch (soft-delete, still preserved for historical elections)."""
        batch.status = RegistrarImportBatch.Status.ARCHIVED
        batch.save(update_fields=["status", "updated_at"])
        logger.info("Registrar batch archived: %s (%s)", batch.name, batch.pk)

    @staticmethod
    @transaction.atomic
    def assign_batch_to_election(
        election: Election,
        batch: RegistrarImportBatch,
    ) -> None:
        """Link a registrar batch to an election."""
        if election.is_voter_roll_finalized:
            raise VoterRollError("Cannot change batch: voter roll is already finalized.")
        election.registrar_batch = batch
        election.save(update_fields=["registrar_batch", "updated_at"])
        logger.info(
            "Registrar batch %s assigned to election %s",
            batch.pk, election.pk,
        )
