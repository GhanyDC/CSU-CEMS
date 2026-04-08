# RESET_FIX_RUN_01_OUTPUT

**Date:** 2026-04-09
**Scope:** Fix `generate_pilot_data --clear` ProtectedError when ballots exist
**Starting symptom:** `django.db.models.deletion.ProtectedError: Cannot delete some instances of model 'Candidate' because they are referenced through protected foreign keys: 'BallotSelection.candidate'`

---

## 1. Summary of the Bug

Running `python manage.py generate_pilot_data --clear` after the pilot test (or any voting activity) raised a `ProtectedError`. The `--clear` block deleted records in the wrong order: it tried to delete `Candidate` rows while `BallotSelection` rows still referenced them via a `PROTECT` foreign key.

This was exposed after the stabilization run added voter roll generation to `generate_pilot_data` (making end-to-end pilot tests possible), which meant ballots could actually be cast against the pilot data for the first time.

---

## 2. Root Cause

The clear block in `generate_pilot_data.py` deleted in this order:

```
EligibleVoter → VerificationRecord → Candidate → Position → Election → Student
```

But the FK dependency chain includes:

| Model | FK Target | on_delete |
|-------|-----------|-----------|
| `BallotSelection.candidate` | `Candidate` | **PROTECT** |
| `BallotSelection.position` | `Position` | **PROTECT** |
| `BallotSelection.ballot` | `Ballot` | CASCADE |
| `Ballot.election` | `Election` | **PROTECT** |

When `BallotSelection` rows exist (from voting), deleting `Candidate` or `Position` first triggers `ProtectedError`. The clear block was missing `BallotSelection` and `Ballot` entirely.

---

## 3. Fix Approach

Added `BallotSelection` and `Ballot` deletions at the top of the clear block, before any PROTECT-referencing models are touched. Also added `AuditLog` clearing for a clean development reset.

**Safe deletion order (implemented):**

1. `BallotSelection` - references Candidate, Position, Ballot
2. `Ballot` - references Election
3. `EligibleVoter` - references Election, Student
4. `VerificationRecord` - references Election, Student
5. `Candidate` - references Position
6. `Position` - references Election
7. `Election`
8. `Student`
9. `AuditLog` - no FKs, safe anywhere
10. Admin users (Django User cascade deletes AdminProfile)

The `PROTECT` constraints on `BallotSelection.candidate` and `BallotSelection.position` are intentionally **preserved**. They exist to prevent accidental deletion of election data while ballots reference it. The fix respects this by deleting ballot data first, not by weakening the constraint.

---

## 4. Files Changed

| File | Change |
|------|--------|
| `apps/accounts/management/commands/generate_pilot_data.py` | Added `BallotSelection`, `Ballot`, `AuditLog` imports; fixed clear block to delete in safe FK-dependency order |
| `tests/test_commands.py` | Added 3 new tests: `test_clear_after_ballots_exist`, `test_generate_clear_generate_repeatability`, `test_clear_removes_voter_roll`; added `Ballot`, `BallotSelection`, `EligibleVoter` imports |

No models, migrations, or frozen rules were changed.

---

## 5. Tests Added

| Test | What It Covers |
|------|---------------|
| `test_clear_after_ballots_exist` | Creates pilot data, casts a ballot (Ballot + BallotSelection), then runs `--clear` again. Verifies no ProtectedError and clean slate. |
| `test_generate_clear_generate_repeatability` | Runs generate → clear → generate and verifies fresh data each time with new election PK. |
| `test_clear_removes_voter_roll` | Verifies `--clear` properly removes EligibleVoter records and rebuilds them for the new election. |

---

## 6. Commands to Rerun Locally

```bash
# 1. Run the full automated test suite (355 tests expected)
python -m pytest tests/ -v --tb=short

# 2. Run the fixed command against PostgreSQL
#    (set DJANGO_SETTINGS_MODULE if your shell has test settings persisted)
set DJANGO_SETTINGS_MODULE=config.settings.local
python manage.py generate_pilot_data --clear

# 3. Run the pilot test to verify end-to-end
python run_pilot_test.py

# 4. Run --clear again to confirm repeatability after ballots exist
python manage.py generate_pilot_data --clear
```

---

## 7. Manual Verification Steps

1. Ensure PostgreSQL is running and migrations are applied
2. Run `python manage.py generate_pilot_data --clear` — should succeed
3. Run `python run_pilot_test.py` — creates ballots during phases 8-10
4. Run `python manage.py generate_pilot_data --clear` again — **this was the failing step; should now succeed**
5. Run `python run_pilot_test.py` again — 59/59 should pass

---

## 8. Test Results

| Suite | Result |
|-------|--------|
| `python -m pytest tests/` | **355 passed** in 6.01s (352 original + 3 new) |
| `python run_pilot_test.py` | **59 passed, 0 failed** |
| `generate_pilot_data --clear` (post-ballots) | **Success** — no ProtectedError |
| `generate_pilot_data --clear` (second run) | **Success** — repeatable |

---

## 9. Remaining Risks / Follow-ups

| Item | Severity | Notes |
|------|----------|-------|
| `AuditLog` cleared on `--clear` | Info | Appropriate for dev reset. Production should never use `--clear`. |
| `Ballot.election` is `PROTECT` | Info | Correct — prevents orphaned ballots. Our clear order handles this. |
| Django sessions not cleared | Low | Old login sessions may reference deleted students. Harmless — they'll get 401 on next request. |
| `--clear` is a full wipe | Info | By design — it's a dev reset command, not a selective cleanup. |

---

## 10. Recommended Next Prompt

> Run a full end-to-end pilot test cycle using the browser UI. Start the dev server with `python manage.py runserver`, log in as `eb_head`, start the election from the admin panel, then log in as a student and cast a ballot through the browser. Verify the dashboard, ballot, and results pages render correctly. Report any JS console errors or broken UI flows.
