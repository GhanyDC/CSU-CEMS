# Admin Reconciliation Run 01 — Output

**Date**: 2026-04-10
**Test suite**: 498 passed, 0 failures, 79% coverage

---

## Summary

This run performed a deep reconciliation between the CEMS codebase, admin panel templates, documentation, and the non-negotiable final rules. All inconsistencies between intended behavior and actual implementation were identified and fixed.

---

## Inconsistencies Found and Fixed

### 1. Tally Visibility During Active — Operator & Tally Watcher (CRITICAL)

**Before**: Operator and Tally Watcher received 403 on the `/tally/` endpoint during Active elections. Only EB Head could access tally data.

**After**: All three roles can now access the tally endpoint during Active, but with role-differentiated data:
- **EB Head**: Full per-candidate live tally (unchanged)
- **Operator**: Participation summary only — `redacted: true`, no per-candidate `votes`, no `winner` or `status` fields
- **Tally Watcher**: Participation summary only during Active — same redaction as Operator; full tally after Closed/Published

**Rationale**: The final rules require monitoring data integrated into the Positions & Candidates tab for all roles. A 403 would prevent the tab from loading any participation data.

**Files changed**: `apps/elections/views.py` (lines 449–501)

### 2. Positions & Candidates Tab — No Monitoring Data (CRITICAL)

**Before**: `renderPositions()` in admin_panel.html showed only the static candidate roster for all election states (Draft/Active/Closed/Published). No participation data, no vote counts, no abstain totals during Active/Closed/Published.

**After**: `renderPositions()` is now `async` and fetches tally data from the API when the election is not Draft. It renders:
- A state mode indicator (Active — Live Monitoring / Closed — Review Mode / Published — Final Results)
- Per-position participation bar: participation count, percentage, abstain count
- Per-candidate vote counts and percentages (if not redacted by role)
- A "Participation summary only" badge when data is redacted

**Role-based rendering**:
- EB Head during Active: full per-candidate vote counts on each candidate row
- Operator during Active: participation/abstain per position, no per-candidate votes
- Tally Watcher during Active: same as Operator
- Tally Watcher after Closed: full per-candidate vote counts (same as EB Head)
- Operator after Closed: participation/abstain only, per-candidate votes still redacted

**Files changed**: `templates/frontend/admin_panel.html` (renderPositions function rewritten), `static/css/cems.css` (new `.position-monitoring`, `.cand-votes` styles)

### 3. Test Expectations for Operator/TW Tally During Active

**Before**: Multiple tests expected 403 for Operator and Tally Watcher accessing the tally endpoint during Active elections.

**After**: Tests updated to expect 200 with `redacted: true` response.

**Files changed**:
- `tests/test_hardening.py` — 2 tests updated
- `tests/test_student_voting.py` — 1 test updated
- `tests/test_exports_and_new_features.py` — 1 test updated

### 4. (Already Aligned — No Changes Needed)

The following were verified as already aligned with the final rules:

| Area | Status |
|------|--------|
| Tab structure (4 tabs: Overview, Positions, Voter Roll, Lifecycle) | ✅ Correct |
| No Monitoring tab | ✅ Correct |
| Readiness in Overview, Draft only | ✅ Correct |
| EB Head full tally during Active | ✅ Already implemented |
| Operator cannot manage positions | ✅ EB Head only |
| Operator cannot lifecycle (start/close/publish) | ✅ EB Head only |
| Operator cannot finalize voter roll | ✅ EB Head only |
| Operator can add/delete candidates in Draft | ✅ SETUP_ROLES |
| Tally Watcher read-only (no create/edit/delete) | ✅ Correct |
| Auditor denied on all admin endpoints | ✅ Not in any role list |
| Technical Support denied on all admin endpoints | ✅ Not in any role list |
| Export permissions (Operator: turnout only; TW: turnout + tally) | ✅ Correct |
| College rep filtering in election_ballot() | ✅ Backend enforced |
| Abstain computation (total_ballots - position_participation) | ✅ Correct |
| Candidate photos in admin, ballot, results | ✅ Correct |
| Voter roll page with pipeline, metrics, college breakdown | ✅ Comprehensive |
| Drag-to-reorder positions (EB Head, Draft only) | ✅ Correct |

---

## Code Areas Inspected

| File | Lines Inspected | Changes |
|------|----------------|---------|
| `apps/elections/views.py` | Full file (580+ lines) | Tally endpoint rewritten |
| `apps/elections/admin_views.py` | Full file (1370+ lines) | No changes needed |
| `apps/elections/export_views.py` | Full file (320+ lines) | No changes needed |
| `apps/accounts/decorators.py` | Full file (142 lines) | No changes needed |
| `apps/accounts/models.py` | AdminRole, AdminProfile properties | No changes needed |
| `apps/elections/admin_urls.py` | Full file (30 URL patterns) | No changes needed |
| `apps/elections/services.py` | ResultService, TurnoutService | No changes needed |
| `apps/elections/models.py` | Position, Candidate models | No changes needed |
| `templates/frontend/admin_panel.html` | Full file (1920+ lines) | renderPositions rewritten |
| `templates/frontend/ballot.html` | Full file (327+ lines) | No changes needed |
| `templates/frontend/results.html` | Full file (223+ lines) | No changes needed |
| `static/css/cems.css` | Position block styles | New monitoring CSS added |
| `config/urls.py` | URL routing | No changes needed |
| All 14 test files | Full inspection | 4 tests updated |

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `apps/elections/views.py` | Backend | Tally endpoint: Operator/TW get redacted data during Active (was 403) |
| `templates/frontend/admin_panel.html` | Template | renderPositions: async, fetches tally, shows monitoring data + vote counts |
| `static/css/cems.css` | Styles | `.position-monitoring`, `.cand-votes`, `.vote-count`, `.vote-pct` |
| `tests/test_hardening.py` | Tests | 2 tally visibility tests updated (expect 200 + redacted) |
| `tests/test_student_voting.py` | Tests | 1 tally visibility test updated |
| `tests/test_exports_and_new_features.py` | Tests | 1 tally visibility test updated |
| `tests/test_reconciliation.py` | Tests | NEW: 36 comprehensive reconciliation tests |

---

## Migrations

No new migrations were required. The tally visibility change is purely in view logic.

---

## Tests Added/Updated

### New: `tests/test_reconciliation.py` (36 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| TestTallyVisibilityReconciled | 8 | EB Head/Operator/TW visibility by state (Active/Closed/Draft) |
| TestOperatorRestrictions | 7 | Positions, lifecycle, voter roll, candidate permissions |
| TestTallyWatcherRestrictions | 5 | Read-only enforcement across endpoints |
| TestAuditorDenied | 3 | Auditor blocked from all admin endpoints |
| TestExportPermissionsReconciled | 10 | Export access by role and state |
| TestDraftOnlyEditing | 2 | Candidate add and position reorder blocked outside Draft |
| TestCollegeRepFiltering | 1 | Students see only their own college's candidates |
| TestAbstainComputation | 1 | Abstain = total_ballots - position_participation |

### Updated: 4 existing tests

Changed from expecting 403 to expecting 200 with `redacted: true` for Operator/TW during Active.

---

## Remaining Edge Cases

1. **Turnout PNG export**: Mentioned in the final rules — not currently implemented. Would require a charting library (e.g., matplotlib/Pillow). Recommend as v2 enhancement.
2. **Per-college eligible vs approved breakdown**: Voter roll shows per-college approved counts. Per-college registrar eligible counts require cross-referencing the registrar batch data — currently shown at aggregate level only.
3. **Import history on Voter Roll page**: The pipeline shows current import state but not a timestamped history of all past imports. Sufficient for v1.

---

## Commands to Run Locally

```bash
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Run full test suite
python -m pytest tests/ -q --tb=short

# Run reconciliation tests only
python -m pytest tests/test_reconciliation.py -v

# Start dev server for manual validation
$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
python manage.py runserver
```

---

## Recommended Next Prompt

> Perform student-side hardening: reconcile the student ballot rendering, results display, login flow, and eligibility checks against the final admin-side truth established in this reconciliation run. Verify college representative filtering end-to-end, abstain UI behavior, and student results display including photos, vote counts, and threshold calculation.
