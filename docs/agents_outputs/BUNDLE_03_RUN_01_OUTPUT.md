# Bundle 03: Admin Election Setup Flow — Run 01 Output

**Date:** 2025-07-06
**Bundle:** 03 — Admin Election Setup Flow
**Baseline:** 239 tests passing (Bundle 02), 90% coverage
**Final:** 304 tests passing, 91% coverage

---

## Summary

Bundle 03 implements the **Admin Election Setup Flow** — the workflow that enables non-technical Electoral Board officers to create elections, manage candidates, import voter verification data, and confirm election readiness, all without manual UUID entry or Django admin access.

### Key Capabilities Delivered

1. **Template-driven election creation** — Campus elections auto-generate 13 constitutional positions (President, VP, 12 Senators, 9 College Representatives, Party-List). College elections bulk-create 9 elections with 3 positions each (Governor, Vice Governor, 8 Board Members).
2. **Candidate management in DRAFT** — Add/update/deactivate candidates while the election is in Draft. All modifications are blocked once the election leaves Draft status.
3. **Voter roll workflow via admin API** — CSV upload for verification data, match summary review, voter roll generation, and finalization (EB Head only).
4. **Readiness checks** — Structured 7-point checklist confirming schedule, positions, candidates, verification import, voter roll generation, voter roll finalization, and Draft status.
5. **Role-based access control** — Setup actions require Operator or EB Head. Voter roll finalization requires EB Head only. Read-only views available to Tally Watchers and Auditors. Technical Support role excluded from election setup endpoints.
6. **Guided admin dashboard** — Complete rewrite of `admin_panel.html` with election list, detail view (5 tabs), modals for creation and candidate entry, CSV upload, and readiness display.

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `apps/elections/setup_services.py` | ElectionSetupService (campus/college templates), CandidateManagementService (add/update), ReadinessService (7-point check) |
| `apps/elections/admin_views.py` | 12 admin API endpoints — list, detail, create campus/college, add/update candidate, voter roll import/summary/generate/finalize, readiness check |
| `apps/elections/admin_urls.py` | URL routing for admin setup endpoints under `admin_elections` namespace |
| `tests/test_admin_setup.py` | 65 tests — services, API endpoints, role enforcement, integration flows |

### Modified Files

| File | Change |
|------|--------|
| `config/urls.py` | Added `path("api/admin/elections/setup/", include("apps.elections.admin_urls"))` |
| `apps/frontend/views.py` | Expanded `bootstrap_admin` context with `is_eb_head`, `is_operator`, `is_read_only` |
| `templates/frontend/admin_panel.html` | Complete rewrite — election list + detail dashboard with 5 tabs, modals, CSV upload, role-gated actions |

### Backup Files

| File | Purpose |
|------|---------|
| `templates/frontend/admin_panel_old.html` | Backup of original lifecycle-only admin panel |

### No New Migrations

Bundle 03 introduces no model changes. All new functionality works with the existing schema from Bundles 01-02.

---

## API Endpoints Added

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/admin/elections/setup/list/` | EB Head, Operator, Tally, Auditor | List all elections |
| GET | `/api/admin/elections/setup/<id>/` | EB Head, Operator, Tally, Auditor | Full election detail with positions, candidates, voter roll |
| POST | `/api/admin/elections/setup/create-campus/` | EB Head, Operator | Create campus election from template (13 positions) |
| POST | `/api/admin/elections/setup/create-college/` | EB Head, Operator | Bulk-create college elections (9 × 3 positions) |
| POST | `/api/admin/elections/setup/<id>/candidates/add/` | EB Head, Operator | Add candidate (DRAFT only) |
| POST | `/api/admin/elections/setup/<id>/candidates/<cid>/update/` | EB Head, Operator | Update candidate (DRAFT only) |
| POST | `/api/admin/elections/setup/<id>/voter-roll/import/` | EB Head, Operator | Upload CSV verification data |
| GET | `/api/admin/elections/setup/<id>/voter-roll/summary/` | EB Head, Operator, Tally, Auditor | Voter roll match summary + unmatched records |
| POST | `/api/admin/elections/setup/<id>/voter-roll/generate/` | EB Head, Operator | Generate EligibleVoter records from matches |
| POST | `/api/admin/elections/setup/<id>/voter-roll/finalize/` | **EB Head only** | Lock voter roll (irreversible) |
| GET | `/api/admin/elections/setup/<id>/readiness/` | EB Head, Operator, Tally, Auditor | 7-point readiness checklist |

---

## Test Results

```
304 passed in 5.93s
Coverage: 91%
```

### New Tests (65 total)

| Test Class | Count | What It Covers |
|------------|-------|----------------|
| TestElectionSetupServiceCampus | 5 | Campus template, 13 positions, categories, validation |
| TestElectionSetupServiceCollege | 7 | Bulk creation, 9 colleges × 3 positions, naming, subsets, validation |
| TestCandidateManagementService | 9 | Add/update/toggle, DRAFT enforcement, uniqueness, empty name |
| TestReadinessService | 5 | Empty/ready/partial states, missing candidates, unfinalized roll |
| TestListElectionsAPI | 5 | Operator/Head/Tally access, unauth/tech rejected |
| TestElectionDetailAPI | 2 | Full detail response, 404 for invalid UUID |
| TestCreateCampusElectionAPI | 4 | Operator/Head creation, missing fields, access control |
| TestCreateCollegeElectionsAPI | 2 | Bulk creation, missing fields |
| TestAddCandidateAPI | 3 | Add candidate, blocked in ACTIVE, invalid position |
| TestUpdateCandidateAPI | 2 | Update candidate, blocked in ACTIVE |
| TestVoterRollImportAPI | 3 | CSV upload, no file, missing student_id column |
| TestVoterRollSummaryAPI | 1 | Match summary with unmatched records |
| TestGenerateVoterRollAPI | 1 | Generate voter roll from matched records |
| TestFinalizeVoterRollAPI | 3 | EB Head can finalize, Operator cannot, empty roll rejected |
| TestReadinessCheckAPI | 2 | Partial readiness, fully ready election |
| TestRoleEnforcement | 6 | Systematic role checks across all endpoint categories |
| TestAdminPanelPage | 3 | Auth required, renders for operator, bootstraps admin context |
| TestCompleteSetupFlow | 2 | End-to-end campus setup (11 steps), bulk college setup |

### Coverage Highlights

| Module | Coverage |
|--------|----------|
| `apps/elections/setup_services.py` | 97% |
| `apps/elections/admin_views.py` | 85% |
| `apps/elections/admin_urls.py` | 100% |
| `apps/elections/models.py` | 100% |
| `apps/elections/services.py` | 99% |

---

## Architecture Decisions

1. **Separate `admin_views.py`** — Admin setup endpoints are in a dedicated file, not mixed with student-facing `views.py`. This keeps concerns cleanly separated.

2. **Service layer pattern** — `setup_services.py` contains all business logic (template application, DRAFT enforcement, readiness checks). Views are thin dispatchers.

3. **CSV upload via multipart/form-data** — Voter roll import accepts a real file upload (not JSON-encoded rows), enabling the admin UI to use a standard file picker.

4. **No model changes** — All setup workflow functionality is built on top of the existing Election, Position, Candidate, VerificationRecord, and EligibleVoter models from Bundles 01-02.

5. **Template constants** — Campus and college position templates are defined as module-level constants in `setup_services.py`, matching the constitutional structure from `KNOWN_DECISIONS_COMPACT.md`.

---

## Manual Verification Steps

### 1. Campus Election Creation
```
1. Log in as Operator at /admin/login/
2. Navigate to /admin-panel/
3. Click "Create Campus Election"
4. Enter name, start/end times
5. Verify 13 positions created (President, VP, Senator, 9 College Reps, Party-List)
```

### 2. College Elections Bulk Creation
```
1. Click "Create College Elections"
2. Enter name prefix and schedule
3. Verify 9 separate elections created, each with Governor, Vice Governor, Board Members
```

### 3. Candidate Management
```
1. Open a draft election
2. Add candidates to each position
3. Update a candidate's party
4. Deactivate a candidate
5. Verify candidates cannot be added/modified after election is started
```

### 4. Voter Roll Import & Finalization
```
1. Prepare CSV with student_id column
2. Upload via Voter Roll tab
3. Review match summary (matched vs unmatched)
4. Click "Generate Voter Roll"
5. As EB Head, click "Finalize Voter Roll"
6. Verify Operator cannot finalize
```

### 5. Readiness Check
```
1. Open Readiness tab for an election
2. Verify all 7 checks display with pass/fail
3. Resolve blocking issues and re-check
4. Confirm "ready" status when all checks pass
```

---

## Open Issues

None. All acceptance criteria from `BUNDLE_03_ADMIN_ELECTION_SETUP_FLOW.md` are met.

---

## Recommended Next Prompt

> **Implement Bundle 04 only.**
> Read these files first (they are authoritative):
> 1. `docs/SYSTEM_SOURCE_OF_TRUTH.md`
> 2. `docs/IMPLEMENTATION_ROADMAP.md`
> 3. `docs/KNOWN_DECISIONS_COMPACT.md`
> 4. `docs/BUNDLE_04_STUDENT_VOTING_RESULTS_AND_MONITORING.md`
> 5. `docs/agents_outputs/BUNDLE_03_RUN_01_OUTPUT.md`
>
> The codebase currently has 304 passing tests across Bundles 01-03 with 91% coverage. Do not break existing tests.
