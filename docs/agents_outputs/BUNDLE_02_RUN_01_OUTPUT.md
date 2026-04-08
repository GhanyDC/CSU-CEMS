# Bundle 02 — Core Election Domain & Voter Roll: Run 01 Output

**Date:** 2025-01-09  
**Status:** ✅ Complete  
**Tests:** 239 passed (0 failed), 90% coverage  

---

## Summary

Implemented the per-election voter roll pipeline, election type scoping (campus/college), and eligibility enforcement. Elections now require a finalized voter roll before starting, and only students on the voter roll can cast ballots.

---

## New Files

| File | Purpose |
|------|---------|
| `apps/elections/constants.py` | `OFFICIAL_COLLEGES` — authoritative list of 9 recognized colleges |
| `apps/elections/management/__init__.py` | Package init |
| `apps/elections/management/commands/__init__.py` | Package init |
| `apps/elections/management/commands/import_verification.py` | CLI command for CSV verification form import |
| `apps/elections/migrations/0004_eligiblevoter_verificationrecord_election_college_and_more.py` | Migration for all Bundle 02 schema changes |
| `tests/test_voter_roll.py` | 41 tests covering voter roll service, models, and command |

## Modified Files

| File | Changes |
|------|---------|
| `apps/elections/models.py` | Added `ElectionType` choices, `election_type`/`college`/`voter_roll_finalized_at`/`voter_roll_finalized_by` fields to Election. Added `COLLEGE_EXECUTIVE`/`COLLEGE_BOARD` to Position.Category. Added `EligibleVoter` and `VerificationRecord` models. |
| `apps/elections/services.py` | Added `VoterRollService` (import, match, generate, finalize, counts). Updated `ElectionLifecycleService.start_election()` to gate on finalized voter roll. Updated `ResultService._determine_winner()` for college position categories. Added `VoterRollError` and `ElectionNotReadyError`. |
| `apps/voting/services.py` | Added `EligibleVoter` check in `BallotService.cast_ballot()`. Added `VoterNotEligibleError`. |
| `apps/voting/views.py` | Handle `VoterNotEligibleError` → 403 response. |
| `apps/elections/views.py` | Handle `ElectionNotReadyError` → 409 response. |
| `apps/elections/admin.py` | Registered `EligibleVoter` and `VerificationRecord` admin classes. Updated `ElectionAdmin` with new fields. |
| `apps/accounts/management/commands/generate_pilot_data.py` | Uses `OFFICIAL_COLLEGES` constant. Updated `COURSES_BY_COLLEGE` mapping. |
| `conftest.py` | Added `make_eligible()` and `finalize_election_voter_roll()` helpers. |
| `tests/test_voting.py` | All tests create eligible voters. Added `TestVoterEligibility` class (3 tests). |
| `tests/test_lifecycle.py` | All start-election tests include voter roll setup. Added 2 voter-roll-gate tests. |
| `tests/test_integration.py` | Added voter roll setup to integration flows. |
| `tests/test_views.py` | Added voter roll setup for cast-ballot and lifecycle view tests. |
| `tests/test_admin_auth.py` | Added voter roll setup for `test_eb_head_can_start`. |
| `tests/test_commands.py` | Updated position count assertion (12 → 13 for 9 colleges). |

---

## New Models

### `EligibleVoter`
- `election` FK → Election
- `student` FK → Student (PROTECT)
- `college_snapshot` — frozen college at enrollment time
- `created_at` — auto timestamp
- UniqueConstraint: (election, student)

### `VerificationRecord`
- `election` FK → Election
- `student_id_input`, `full_name_input`, `college_input` — raw form data
- `matched_student` FK → Student (SET_NULL, nullable)
- `status` — PENDING / MATCHED / UNMATCHED / DUPLICATE
- `imported_at` — auto timestamp
- UniqueConstraint: (election, student_id_input)

---

## New Service: `VoterRollService`

| Method | Description |
|--------|-------------|
| `import_verification(election, rows)` | Bulk-import verification form rows, match against Student table |
| `get_match_summary(election)` | Return counts by status |
| `get_unmatched_records(election)` | Queryset of unmatched records |
| `generate_voter_roll(election)` | Create EligibleVoters from matched records; college-filters for college elections |
| `finalize_voter_roll(election, finalized_by)` | Lock the voter roll (select_for_update) |
| `get_approved_count(election)` | Total eligible voters |
| `get_approved_count_by_college(election)` | Eligible voters grouped by college |

---

## Key Enforcement Rules

1. **Voter roll must be finalized before `DRAFT → ACTIVE` transition** — `ElectionLifecycleService.start_election()` raises `ElectionNotReadyError` otherwise.
2. **Only students on the voter roll can cast ballots** — `BallotService.cast_ballot()` raises `VoterNotEligibleError` (HTTP 403) otherwise.
3. **Finalized voter rolls are immutable** — `import_verification()` and `generate_voter_roll()` reject operations on finalized elections.
4. **College elections filter voters by college** — `generate_voter_roll()` only includes students whose college matches `election.college`.
5. **College snapshot is frozen at enrollment** — `EligibleVoter.college_snapshot` captures the student's college at voter roll generation time.

---

## Test Coverage Highlights

| Area | Tests | Key Scenarios |
|------|-------|---------------|
| Election type validation | 6 | Campus/college creation, clean() enforcement, invalid college |
| EligibleVoter model | 3 | Creation, uniqueness, cross-election |
| VerificationRecord model | 3 | Creation, uniqueness, cross-election |
| Import verification | 6 | Match/unmatch, duplicates, finalization block, empty IDs |
| Generate voter roll | 6 | Basic generation, idempotency, college filtering, snapshot, finalization block |
| Finalize voter roll | 3 | Basic finalization, double-finalize block, empty roll block |
| Counts & summaries | 4 | Approved count, by-college count, match summary, unmatched queryset |
| Management command | 4 | Basic import, dry-run, file not found, invalid election ID |
| Position categories | 3 | College executive/board existence, position creation |
| Official colleges | 3 | Count, inclusion, naming convention |

---

## Open Items for Future Bundles

- **Admin UI for voter roll management** — Currently CLI-only via `import_verification` command. Bundle 03 should add admin panel views for import, review, and finalize.
- **Batch verification form upload** — Current implementation accepts pre-parsed rows. A file upload endpoint with CSV parsing is needed.
- **Voter roll audit logging** — Import/generate/finalize operations are logged via Python logging but not yet in the AuditLog model.
