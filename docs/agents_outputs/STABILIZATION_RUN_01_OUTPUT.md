# STABILIZATION_RUN_01_OUTPUT

**Date:** 2026-04-09
**Scope:** Project-wide stabilization, cleanup, and bug-fixing pass
**Starting symptom:** `GET /api/elections/mine/` raises `django.db.utils.ProgrammingError: relation "elections_eligiblevoter" does not exist`

---

## 1. Summary

The CEMS project had all code implemented across Bundles 01-04 with 352 tests passing against SQLite `:memory:`, but the **local PostgreSQL database was missing 3 critical migrations** from Bundles 01-02. This meant all student-facing endpoints, voter roll management, and admin authentication were broken against the actual development database. Additionally, the pilot test script (`run_pilot_test.py`) used pre-Bundle-01 student auth patterns for admin lifecycle operations, and `generate_pilot_data` did not create admin users or voter roll data.

**After stabilization:** All migrations applied, pilot data command creates a complete development environment, pilot test passes 59/59 checks, automated test suite passes 352/352 tests.

---

## 2. Root Causes Identified

### RC-1: Missing PostgreSQL Migrations (CRITICAL)
**Symptom:** `ProgrammingError: relation "elections_eligiblevoter" does not exist`
**Root Cause:** Three migrations were never applied to the local PostgreSQL database:
- `accounts.0004_admin_profile_model` — AdminProfile table (Bundle 01)
- `elections.0004_eligiblevoter_verificationrecord_election_college_and_more` — EligibleVoter + VerificationRecord tables (Bundle 02)
- `audit.0003_admin_audit_event_types` — Admin audit event types (Bundle 02)

**Why:** Tests run against SQLite `:memory:` (via `config.settings.test`) which creates tables fresh each run. The developer never ran `python manage.py migrate` against the local PostgreSQL after implementing Bundles 01-02.

**Fix:** Applied `python manage.py migrate --settings=config.settings.local`. All 3 migrations applied successfully.

### RC-2: Incomplete Pilot Data Generation
**Symptom:** Even after migrations, the end-to-end flow was broken because:
- No admin users existed (no Django User + AdminProfile records)
- No voter roll data existed (no VerificationRecord or EligibleVoter records)
- Students had no visibility into elections (EligibleVoter is required for all student-facing endpoints)

**Fix:** Updated `generate_pilot_data.py` to create:
- 3 admin users (EB Head, Operator, Tally Watcher) with AdminProfiles
- VerificationRecord entries for all students (simulates registrar import)
- EligibleVoter entries for all students
- Finalized voter roll (required before DRAFT → ACTIVE transition)
- `--clear` flag now also cleans EligibleVoter, VerificationRecord, and admin users

### RC-3: Broken Pilot Test Script
**Symptom:** `run_pilot_test.py` used student auth (`/api/auth/login/` with student_id + DOB) for admin lifecycle actions, which fails because lifecycle endpoints require `@admin_login_required` (Django User session auth + AdminProfile).

**Fix:** Rewrote `run_pilot_test.py` to:
- Use admin auth (`/api/admin/auth/login/`) for lifecycle endpoints
- Pick test voters from EligibleVoter records (not arbitrary Student records)
- Test new Bundle 04 endpoints (`/api/elections/mine/`, `/api/elections/<id>/ballot/`)
- Test admin role enforcement (Operator cannot do lifecycle)
- Test admin auth validation (invalid admin credentials)
- Verify voter roll finalization is preserved across DRAFT → ACTIVE transition
- 59 checks covering all 19 test phases

---

## 3. Changes Made

### Files Modified

| File | Change |
|------|--------|
| `apps/accounts/management/commands/generate_pilot_data.py` | Added admin user creation (3 users), voter roll generation (verification records + eligible voters + finalization), updated `--clear` to clean all related data |
| `run_pilot_test.py` | Full rewrite: admin auth for lifecycle, voter roll-aware voter selection, Bundle 04 endpoint testing, admin role enforcement tests, 19 phases / 59 checks |

### Files Deleted

| File | Reason |
|------|--------|
| `_check_db.py` | Temporary diagnostic script from inspection phase |

### Database Changes

| Migration | Status |
|-----------|--------|
| `accounts.0004_admin_profile_model` | Applied (was missing) |
| `elections.0004_eligiblevoter_verificationrecord_election_college_and_more` | Applied (was missing) |
| `audit.0003_admin_audit_event_types` | Applied (was missing) |

No new migrations created. All existing migrations applied cleanly.

---

## 4. Commands for Fresh Setup

```bash
# 1. Ensure PostgreSQL is running on localhost:5432
# 2. Activate virtual environment
# 3. Apply all migrations
python manage.py migrate --settings=config.settings.local

# 4. Generate complete pilot data
python manage.py generate_pilot_data --clear --settings=config.settings.local
# Output will show admin credentials:
#   EB Head:       eb_head / pilot_admin_pass
#   Operator:      operator1 / pilot_admin_pass
#   Tally Watcher: tally_watcher1 / pilot_admin_pass

# 5. Run automated test suite
python -m pytest tests/ -v --tb=short

# 6. Run pilot test (end-to-end)
# Note: Set DJANGO_SETTINGS_MODULE=config.settings.local in your shell
python run_pilot_test.py

# 7. Start dev server
python manage.py runserver --settings=config.settings.local
```

---

## 5. Test Results

### Automated Test Suite (pytest)
- **352 passed** in 6.49s
- **91% code coverage**
- Settings: `config.settings.test` (SQLite `:memory:`)

### Pilot Test (run_pilot_test.py)
- **59 passed, 0 failed** out of 59 checks
- Settings: `config.settings.local` (PostgreSQL)
- Phases covered:
  1. Unauthenticated access (5 checks)
  2. Invalid credentials (2 checks)
  3. Admin login via Django auth (1 check)
  4. Non-admin lifecycle rejection (4 checks)
  5. DRAFT state visibility (4 checks)
  6. Admin starts election (2 checks)
  7. Active state: /mine/, /ballot/, /current/, /status/ (11 checks)
  8. Ballot casting + has_voted reflection (3 checks)
  9. Double vote prevention + audit (2 checks)
  10. Second voter casting (1 check)
  11. Election close (2 checks)
  12. Vote after close (1 check)
  13. Invalid state transitions (2 checks)
  14. Publish results (2 checks)
  15. View published results + /mine/ visibility (4 checks)
  16. Post-publish transition rejection (1 check)
  17. Brute-force lockout (2 checks)
  18. Admin auth validation + role enforcement (3 checks)
  19. Audit log completeness (7 checks)

---

## 6. Frozen Rules Preserved

All frozen election rules from the authoritative documents remain unchanged:

| Rule | Status |
|------|--------|
| 9 official colleges | Unchanged |
| 2 election types (campus/college) | Unchanged |
| Separate admin auth (Django User + AdminProfile) | Unchanged |
| 4-state lifecycle (DRAFT → ACTIVE → CLOSED → PUBLISHED) | Unchanged |
| EB Head-only lifecycle transitions | Unchanged |
| Voter roll = registrar import ∩ verification form | Unchanged |
| 50%+1 threshold for executive positions | Unchanged |
| One ballot per election per student | Unchanged |
| College isolation for college elections | Unchanged |
| No live candidate tallies during Active | Unchanged |
| SHA-256 hashed student_id in ballots | Unchanged |
| Voter roll must be finalized before starting election | Unchanged |

---

## 7. Known Risks & Remaining Work

| Item | Severity | Notes |
|------|----------|-------|
| `MANUAL_PILOT_TESTING_GUIDE.md` references pre-Bundle-01 auth patterns | Low | Superseded by `MANUAL_TESTING_CHECKLIST.md` |
| `run_pilot_test.py` uses `RATELIMIT_ENABLE = False` override | Info | Necessary for brute-force test isolation |
| Test coverage for `admin_views.py` is 85% | Low | Setup endpoints are integration-tested via pilot test |
| `frontend/views.py` coverage is 47% | Low | Template rendering views; tested via browser |
| Audit log counts accumulate across pilot test runs | Info | Use `--clear` flag to reset data |
