"""Hybrid election services for onsite canvass imports and combined summaries."""
from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    HybridImportBatch,
    OnsiteParticipation,
    OnsiteTally,
    Position,
)
from apps.voting.models import Ballot, BallotSelection


class HybridElectionError(Exception):
    """Raised when hybrid election imports or workflows are invalid."""

    def __init__(self, message: str, *, summary: dict | None = None) -> None:
        super().__init__(message)
        self.summary = summary or {}


class HybridElectionService:
    """Import, validation, and reporting helpers for hybrid elections."""

    ROSTER_REQUIRED_COLUMNS = {"student_id"}
    TALLY_REQUIRED_COLUMNS = {
        "position_id",
        "position_title",
        "candidate_id",
        "candidate_name",
        "onsite_votes",
    }

    @staticmethod
    def _normalize_headers(rows: list[dict]) -> set[str]:
        if not rows:
            return set()
        return {str(key).strip() for key in rows[0].keys() if key is not None}

    @staticmethod
    def _serialize_batch(batch: HybridImportBatch | None) -> dict:
        if not batch:
            return {
                "status": "missing",
                "batch_id": None,
                "source_filename": "",
                "imported_by": "",
                "created_at": None,
                "activated_at": None,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "overlap_count": 0,
                "validation_summary": {},
            }
        return {
            "status": batch.status,
            "batch_id": str(batch.pk),
            "source_filename": batch.source_filename,
            "imported_by": batch.imported_by,
            "created_at": batch.created_at.isoformat(),
            "activated_at": batch.activated_at.isoformat() if batch.activated_at else None,
            "total_rows": batch.total_rows,
            "valid_rows": batch.valid_rows,
            "invalid_rows": batch.invalid_rows,
            "overlap_count": batch.overlap_count,
            "validation_summary": batch.validation_summary or {},
        }

    @classmethod
    def _record_batch(
        cls,
        *,
        election: Election,
        batch_type: str,
        status: str,
        imported_by: str,
        source_filename: str,
        total_rows: int,
        valid_rows: int,
        invalid_rows: int,
        overlap_count: int = 0,
        validation_summary: dict | None = None,
    ) -> HybridImportBatch:
        return HybridImportBatch.objects.create(
            election=election,
            batch_type=batch_type,
            status=status,
            imported_by=imported_by,
            source_filename=source_filename,
            total_rows=total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            overlap_count=overlap_count,
            validation_summary=validation_summary or {},
            activated_at=timezone.now() if status == HybridImportBatch.Status.ACTIVE else None,
        )

    @classmethod
    def _require_hybrid_closed(cls, election: Election) -> None:
        if not election.is_hybrid:
            raise HybridElectionError("Onsite imports are only available for hybrid elections.")
        if election.status != Election.Status.CLOSED:
            raise HybridElectionError(
                "Onsite imports are only allowed while the election is in Closed status."
            )

    @classmethod
    def get_active_batch(cls, election: Election, batch_type: str) -> HybridImportBatch | None:
        return (
            HybridImportBatch.objects.filter(
                election=election,
                batch_type=batch_type,
                status=HybridImportBatch.Status.ACTIVE,
            )
            .order_by("-activated_at", "-created_at")
            .first()
        )

    @classmethod
    def get_latest_batch(cls, election: Election, batch_type: str) -> HybridImportBatch | None:
        return (
            HybridImportBatch.objects.filter(
                election=election,
                batch_type=batch_type,
            )
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def has_required_imports(cls, election: Election) -> bool:
        return cls.get_publish_readiness(election)["ready"]

    @classmethod
    def _build_tally_limit_errors(
        cls,
        election: Election,
        *,
        onsite_participant_count: int,
        position_vote_totals: dict[str, int],
    ) -> list[str]:
        """Validate aggregate onsite votes against the imported onsite turnout."""
        position_map = {
            str(position.pk): position
            for position in Position.objects.filter(election=election).only(
                "pk", "title", "max_selections"
            )
        }
        errors: list[str] = []
        for position_id, total_votes in position_vote_totals.items():
            position = position_map.get(str(position_id))
            if position is None:
                errors.append(
                    f"Onsite tally references an unknown position: {position_id}."
                )
                continue

            max_allowed_votes = onsite_participant_count * position.max_selections
            if total_votes > max_allowed_votes:
                errors.append(
                    f"Onsite tally total for '{position.title}' exceeds the maximum of "
                    f"{max_allowed_votes} vote(s) for {onsite_participant_count} "
                    f"onsite participant(s)."
                )
        return errors

    @classmethod
    def get_publish_readiness(cls, election: Election) -> dict:
        """Return whether the active hybrid imports are safe to publish."""
        if not election.is_hybrid:
            return {"ready": True, "errors": []}

        roster_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.ROSTER)
        tally_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.TALLY)
        errors: list[str] = []

        if roster_batch is None:
            errors.append("An active onsite roster import is required.")
        if tally_batch is None:
            errors.append("An active onsite tally import is required.")

        if roster_batch is not None and tally_batch is not None:
            if tally_batch.created_at < roster_batch.created_at:
                errors.append(
                    "The active onsite tally predates the current onsite roster import. "
                    "Re-import the onsite tally for the current roster."
                )

            onsite_participant_count = roster_batch.participations.count()
            position_vote_totals = {
                str(row["position_id"]): int(row["total_votes"] or 0)
                for row in tally_batch.tallies.values("position_id").annotate(
                    total_votes=Sum("onsite_votes")
                )
            }
            errors.extend(
                cls._build_tally_limit_errors(
                    election,
                    onsite_participant_count=onsite_participant_count,
                    position_vote_totals=position_vote_totals,
                )
            )

        return {"ready": not errors, "errors": errors}

    @classmethod
    def build_tally_template_rows(cls, election: Election) -> list[dict]:
        candidates = (
            Candidate.objects.filter(position__election=election, is_active=True)
            .select_related("position")
            .order_by("position__order", "position__title", "full_name")
        )
        return [
            {
                "position_id": str(candidate.position_id),
                "position_title": candidate.position.title,
                "candidate_id": str(candidate.pk),
                "candidate_name": candidate.full_name,
                "onsite_votes": "",
            }
            for candidate in candidates
        ]

    @classmethod
    def compute_turnout_breakdown(cls, election: Election) -> dict:
        eligible_qs = EligibleVoter.objects.filter(election=election).select_related("student")
        eligible_voters = list(eligible_qs)
        total_eligible = len(eligible_voters)

        online_ballots = list(
            Ballot.objects.filter(election=election).only("hashed_student_id")
        )
        online_hashes = {ballot.hashed_student_id for ballot in online_ballots}
        online_voted = len(online_hashes)

        roster_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.ROSTER)
        onsite_participations = list(
            roster_batch.participations.select_related("student")
            if roster_batch
            else OnsiteParticipation.objects.none()
        )
        onsite_voted = len(onsite_participations)
        combined_voted = online_voted + onsite_voted

        online_by_college: dict[str, int] = defaultdict(int)
        eligible_by_college: dict[str, int] = defaultdict(int)
        for voter in eligible_voters:
            college_name = voter.college_snapshot or ""
            eligible_by_college[college_name] += 1
            hashed_id = Ballot.hash_student_id(voter.student.student_id, str(election.pk))
            if hashed_id in online_hashes:
                online_by_college[college_name] += 1

        onsite_by_college: dict[str, int] = defaultdict(int)
        for participation in onsite_participations:
            onsite_by_college[participation.student.college or ""] += 1

        college_rows = []
        for college_name in sorted(eligible_by_college):
            eligible_count = eligible_by_college[college_name]
            online_count = online_by_college.get(college_name, 0)
            onsite_count = onsite_by_college.get(college_name, 0)
            combined_count = online_count + onsite_count
            college_rows.append(
                {
                    "college": college_name,
                    "eligible": eligible_count,
                    "online_voted": online_count,
                    "onsite_voted": onsite_count,
                    "combined_voted": combined_count,
                    "online_percentage": round(
                        (online_count / eligible_count * 100) if eligible_count else 0, 2
                    ),
                    "onsite_percentage": round(
                        (onsite_count / eligible_count * 100) if eligible_count else 0, 2
                    ),
                    "combined_percentage": round(
                        (combined_count / eligible_count * 100) if eligible_count else 0, 2
                    ),
                }
            )

        has_official_onsite_turnout = election.is_hybrid and roster_batch is not None
        official_total_voted = combined_voted if has_official_onsite_turnout else online_voted
        official_turnout_percentage = round(
            (official_total_voted / total_eligible * 100) if total_eligible else 0,
            2,
        )

        return {
            "total_eligible": total_eligible,
            "online_voted": online_voted,
            "onsite_voted": onsite_voted,
            "combined_voted": combined_voted,
            "has_official_onsite_turnout": has_official_onsite_turnout,
            "official_total_voted": official_total_voted,
            "official_turnout_percentage": official_turnout_percentage,
            "by_college": college_rows,
        }

    @classmethod
    def build_hybrid_summary(cls, election: Election) -> dict:
        turnout = cls.compute_turnout_breakdown(election)
        latest_roster = cls.get_latest_batch(election, HybridImportBatch.BatchType.ROSTER)
        latest_tally = cls.get_latest_batch(election, HybridImportBatch.BatchType.TALLY)
        active_roster = cls.get_active_batch(election, HybridImportBatch.BatchType.ROSTER)
        active_tally = cls.get_active_batch(election, HybridImportBatch.BatchType.TALLY)
        readiness = cls.get_publish_readiness(election)

        return {
            "mode": election.voting_mode,
            "is_hybrid": election.is_hybrid,
            "can_import": election.is_hybrid and election.status == Election.Status.CLOSED,
            "ready_to_publish": readiness["ready"],
            "publish_blockers": readiness["errors"],
            "roster_import": {
                "active": cls._serialize_batch(active_roster),
                "latest": cls._serialize_batch(latest_roster),
            },
            "tally_import": {
                "active": cls._serialize_batch(active_tally),
                "latest": cls._serialize_batch(latest_tally),
            },
            "turnout": {
                "total_eligible": turnout["total_eligible"],
                "online_voted": turnout["online_voted"],
                "onsite_voted": turnout["onsite_voted"],
                "combined_voted": turnout["combined_voted"],
                "online_percentage": round(
                    (turnout["online_voted"] / turnout["total_eligible"] * 100)
                    if turnout["total_eligible"]
                    else 0,
                    2,
                ),
                "onsite_percentage": round(
                    (turnout["onsite_voted"] / turnout["total_eligible"] * 100)
                    if turnout["total_eligible"]
                    else 0,
                    2,
                ),
                "combined_percentage": round(
                    (turnout["combined_voted"] / turnout["total_eligible"] * 100)
                    if turnout["total_eligible"]
                    else 0,
                    2,
                ),
                "official_total_voted": turnout["official_total_voted"],
                "official_turnout_percentage": turnout["official_turnout_percentage"],
            },
        }

    @classmethod
    @transaction.atomic
    def import_onsite_roster(
        cls,
        election: Election,
        rows: list[dict],
        *,
        source_filename: str = "",
        imported_by: str = "",
    ) -> dict:
        cls._require_hybrid_closed(election)

        headers = cls._normalize_headers(rows)
        missing_headers = sorted(cls.ROSTER_REQUIRED_COLUMNS - headers)
        if missing_headers:
            summary = {
                "errors": [
                    f"Missing required column(s): {', '.join(missing_headers)}."
                ]
            }
            cls._record_batch(
                election=election,
                batch_type=HybridImportBatch.BatchType.ROSTER,
                status=HybridImportBatch.Status.FAILED,
                imported_by=imported_by,
                source_filename=source_filename,
                total_rows=len(rows),
                valid_rows=0,
                invalid_rows=len(rows),
                validation_summary=summary,
            )
            raise HybridElectionError(summary["errors"][0], summary=summary)

        eligible_map = {
            voter.student.student_id: voter.student
            for voter in EligibleVoter.objects.filter(election=election).select_related("student")
        }
        online_hashes = set(
            Ballot.objects.filter(election=election).values_list("hashed_student_id", flat=True)
        )

        seen_student_ids: set[str] = set()
        duplicate_ids: list[str] = []
        ineligible_ids: list[str] = []
        overlap_ids: list[str] = []
        missing_student_id_rows = 0
        valid_students = []

        for row in rows:
            student_id = (row.get("student_id") or "").strip()
            if not student_id:
                missing_student_id_rows += 1
                continue
            if student_id in seen_student_ids:
                duplicate_ids.append(student_id)
                continue
            seen_student_ids.add(student_id)

            student = eligible_map.get(student_id)
            if not student:
                ineligible_ids.append(student_id)
                continue

            hashed_id = Ballot.hash_student_id(student_id, str(election.pk))
            if hashed_id in online_hashes:
                overlap_ids.append(student_id)
                continue

            valid_students.append(student)

        errors = []
        if missing_student_id_rows:
            errors.append(
                f"{missing_student_id_rows} row(s) are missing a student_id value."
            )
        if duplicate_ids:
            errors.append(
                f"Duplicate student_id values found: {', '.join(sorted(duplicate_ids)[:10])}"
                + ("..." if len(duplicate_ids) > 10 else "")
            )
        if ineligible_ids:
            errors.append(
                f"Ineligible student_id values found: {', '.join(sorted(ineligible_ids)[:10])}"
                + ("..." if len(ineligible_ids) > 10 else "")
            )
        if overlap_ids:
            errors.append(
                f"These students already voted online: {', '.join(sorted(overlap_ids)[:10])}"
                + ("..." if len(overlap_ids) > 10 else "")
            )
        if not valid_students and not errors:
            errors.append("No valid onsite roster rows were found in the CSV.")

        summary = {
            "errors": errors,
            "duplicate_student_ids": sorted(duplicate_ids),
            "ineligible_student_ids": sorted(ineligible_ids),
            "overlap_student_ids": sorted(overlap_ids),
            "missing_student_id_rows": missing_student_id_rows,
            "valid_student_count": len(valid_students),
        }

        if errors:
            cls._record_batch(
                election=election,
                batch_type=HybridImportBatch.BatchType.ROSTER,
                status=HybridImportBatch.Status.FAILED,
                imported_by=imported_by,
                source_filename=source_filename,
                total_rows=len(rows),
                valid_rows=len(valid_students),
                invalid_rows=len(rows) - len(valid_students),
                overlap_count=len(overlap_ids),
                validation_summary=summary,
            )
            raise HybridElectionError(
                "Onsite roster import failed validation.",
                summary=summary,
            )

        HybridImportBatch.objects.filter(
            election=election,
            batch_type=HybridImportBatch.BatchType.ROSTER,
            status=HybridImportBatch.Status.ACTIVE,
        ).update(status=HybridImportBatch.Status.SUPERSEDED, updated_at=timezone.now())
        superseded_tally_count = HybridImportBatch.objects.filter(
            election=election,
            batch_type=HybridImportBatch.BatchType.TALLY,
            status=HybridImportBatch.Status.ACTIVE,
        ).update(status=HybridImportBatch.Status.SUPERSEDED, updated_at=timezone.now())

        batch = cls._record_batch(
            election=election,
            batch_type=HybridImportBatch.BatchType.ROSTER,
            status=HybridImportBatch.Status.ACTIVE,
            imported_by=imported_by,
            source_filename=source_filename,
            total_rows=len(rows),
            valid_rows=len(valid_students),
            invalid_rows=0,
            overlap_count=0,
            validation_summary=summary,
        )
        OnsiteParticipation.objects.bulk_create(
            [OnsiteParticipation(batch=batch, student=student) for student in valid_students]
        )
        message = f"Imported {len(valid_students)} onsite voter turnout row(s)."
        if superseded_tally_count:
            message += " Existing onsite tally import was cleared; re-import the tally for this roster."

        return {
            "batch": cls._serialize_batch(batch),
            "summary": summary,
            "message": message,
        }

    @classmethod
    @transaction.atomic
    def import_onsite_tally(
        cls,
        election: Election,
        rows: list[dict],
        *,
        source_filename: str = "",
        imported_by: str = "",
    ) -> dict:
        cls._require_hybrid_closed(election)

        roster_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.ROSTER)
        if not roster_batch:
            raise HybridElectionError(
                "Import the onsite voter roster before importing onsite tallies."
            )
        onsite_participant_count = roster_batch.participations.count()

        headers = cls._normalize_headers(rows)
        missing_headers = sorted(cls.TALLY_REQUIRED_COLUMNS - headers)
        if missing_headers:
            summary = {
                "errors": [
                    f"Missing required column(s): {', '.join(missing_headers)}."
                ]
            }
            cls._record_batch(
                election=election,
                batch_type=HybridImportBatch.BatchType.TALLY,
                status=HybridImportBatch.Status.FAILED,
                imported_by=imported_by,
                source_filename=source_filename,
                total_rows=len(rows),
                valid_rows=0,
                invalid_rows=len(rows),
                validation_summary=summary,
            )
            raise HybridElectionError(summary["errors"][0], summary=summary)

        candidates = {
            (str(candidate.position_id), str(candidate.pk)): candidate
            for candidate in (
                Candidate.objects.filter(position__election=election, is_active=True)
                .select_related("position")
                .order_by("position__order", "position__title", "full_name")
            )
        }
        expected_keys = set(candidates.keys())
        seen_keys: set[tuple[str, str]] = set()
        rows_to_create = []
        errors: list[str] = []
        position_vote_totals: dict[str, int] = defaultdict(int)

        for row in rows:
            position_id = str((row.get("position_id") or "")).strip()
            candidate_id = str((row.get("candidate_id") or "")).strip()
            key = (position_id, candidate_id)
            if key in seen_keys:
                errors.append(
                    f"Duplicate tally row found for position_id={position_id} candidate_id={candidate_id}."
                )
                continue
            seen_keys.add(key)

            candidate = candidates.get(key)
            if not candidate:
                errors.append(
                    f"Unknown or inactive candidate row: position_id={position_id}, candidate_id={candidate_id}."
                )
                continue

            position_title = (row.get("position_title") or "").strip()
            candidate_name = (row.get("candidate_name") or "").strip()
            if position_title and position_title != candidate.position.title:
                errors.append(
                    f"Position title mismatch for {candidate.full_name}: expected '{candidate.position.title}'."
                )
                continue
            if candidate_name and candidate_name != candidate.full_name:
                errors.append(
                    f"Candidate name mismatch for candidate_id={candidate_id}: expected '{candidate.full_name}'."
                )
                continue

            votes_raw = str((row.get("onsite_votes") or "")).strip()
            try:
                onsite_votes = int(votes_raw)
            except (TypeError, ValueError):
                errors.append(
                    f"Invalid onsite_votes value for {candidate.full_name}: '{votes_raw}'."
                )
                continue
            if onsite_votes < 0:
                errors.append(f"Negative onsite_votes value is not allowed for {candidate.full_name}.")
                continue

            rows_to_create.append((candidate.position, candidate, onsite_votes))
            position_vote_totals[str(candidate.position_id)] += onsite_votes

        missing_rows = expected_keys - seen_keys
        if missing_rows:
            missing_examples = []
            for position_id, candidate_id in sorted(missing_rows)[:10]:
                candidate = candidates[(position_id, candidate_id)]
                missing_examples.append(
                    f"{candidate.position.title} / {candidate.full_name}"
                )
            errors.append(
                "The tally CSV is missing required candidate rows: "
                + ", ".join(missing_examples)
                + ("..." if len(missing_rows) > 10 else "")
            )
        errors.extend(
            cls._build_tally_limit_errors(
                election,
                onsite_participant_count=onsite_participant_count,
                position_vote_totals=position_vote_totals,
            )
        )

        summary = {
            "errors": errors,
            "onsite_participant_count": onsite_participant_count,
            "expected_candidate_rows": len(expected_keys),
            "received_candidate_rows": len(seen_keys),
            "valid_candidate_rows": len(rows_to_create),
        }

        if errors:
            cls._record_batch(
                election=election,
                batch_type=HybridImportBatch.BatchType.TALLY,
                status=HybridImportBatch.Status.FAILED,
                imported_by=imported_by,
                source_filename=source_filename,
                total_rows=len(rows),
                valid_rows=len(rows_to_create),
                invalid_rows=max(len(rows) - len(rows_to_create), len(errors)),
                validation_summary=summary,
            )
            raise HybridElectionError(
                "Onsite tally import failed validation.",
                summary=summary,
            )

        HybridImportBatch.objects.filter(
            election=election,
            batch_type=HybridImportBatch.BatchType.TALLY,
            status=HybridImportBatch.Status.ACTIVE,
        ).update(status=HybridImportBatch.Status.SUPERSEDED, updated_at=timezone.now())

        batch = cls._record_batch(
            election=election,
            batch_type=HybridImportBatch.BatchType.TALLY,
            status=HybridImportBatch.Status.ACTIVE,
            imported_by=imported_by,
            source_filename=source_filename,
            total_rows=len(rows),
            valid_rows=len(rows_to_create),
            invalid_rows=0,
            validation_summary=summary,
        )
        OnsiteTally.objects.bulk_create(
            [
                OnsiteTally(
                    batch=batch,
                    position=position,
                    candidate=candidate,
                    onsite_votes=onsite_votes,
                )
                for position, candidate, onsite_votes in rows_to_create
            ]
        )

        return {
            "batch": cls._serialize_batch(batch),
            "summary": summary,
            "message": f"Imported onsite tallies for {len(rows_to_create)} candidate row(s).",
        }

    @classmethod
    def get_online_vote_counts(cls, election: Election) -> dict[str, int]:
        return {
            str(row["candidate_id"]): row["votes"]
            for row in (
                BallotSelection.objects.filter(position__election=election)
                .values("candidate_id")
                .annotate(votes=Count("id"))
            )
        }

    @classmethod
    def get_onsite_vote_counts(cls, election: Election) -> dict[str, int]:
        batch = cls.get_active_batch(election, HybridImportBatch.BatchType.TALLY)
        if not batch:
            return {}
        return {
            str(row["candidate_id"]): row["votes"]
            for row in (
                batch.tallies.values("candidate_id")
                .annotate(votes=Sum("onsite_votes"))
            )
        }

    @classmethod
    def get_position_result_context(cls, election: Election) -> dict:
        tally_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.TALLY)
        roster_batch = cls.get_active_batch(election, HybridImportBatch.BatchType.ROSTER)
        return {
            "has_official_onsite_results": election.is_hybrid and tally_batch is not None,
            "has_official_onsite_turnout": election.is_hybrid and roster_batch is not None,
            "online_vote_counts": cls.get_online_vote_counts(election),
            "onsite_vote_counts": cls.get_onsite_vote_counts(election),
            "online_position_participation": {
                str(row["position_id"]): row["count"]
                for row in (
                    BallotSelection.objects.filter(position__election=election)
                    .values("position_id")
                    .annotate(count=Count("ballot_id", distinct=True))
                )
            },
        }
