# Bundle 04 — Student Voting, Results & Monitoring — Run 01 Output

## Summary

Bundle 04 implements the complete student-facing voting flow, election results visibility, and admin monitoring/turnout endpoints. **48 new tests** pass, bringing the total to **352 tests at 90% coverage**, with zero regressions against Bundles 01–03.

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `apps/elections/services.py` | Modified | Added `ResultService.compute_results_with_thresholds()` and `TurnoutService` class |
| `apps/elections/views.py` | Rewritten | 7 student endpoints + 2 admin monitoring endpoints, all eligibility-aware |
| `apps/elections/urls.py` | Modified | Added `mine/` and `<uuid>/ballot/` routes |
| `config/urls.py` | Modified | Added `turnout/` and `tally/` admin monitoring routes |
| `apps/frontend/views.py` | Modified | Added `college` to bootstrap_user context, refactored helper |
| `templates/frontend/dashboard.html` | Rewritten | Multi-election dashboard using `/api/elections/mine/` |
| `templates/frontend/ballot.html` | Modified | Election-specific ballot via `/api/elections/<id>/ballot/` and `?election=` query param |
| `templates/frontend/results.html` | Modified | Election-specific results with threshold/turnout display |
| `tests/test_student_voting.py` | Created | 48 new tests for Bundle 04 features |
| `tests/test_views.py` | Modified | Added `make_eligible()` calls to 7 existing tests for compatibility with eligibility filtering |

---

## New API Endpoints

### Student-Facing

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/elections/mine/` | Returns all elections the student is eligible for (Active + Published), with `has_voted` per election |
| GET | `/api/elections/<uuid>/ballot/` | Returns ballot structure (positions + active candidates) for a specific election; enforces Active status + eligibility + college match |

### Admin Monitoring

| Method | URL | Roles | Description |
|--------|-----|-------|-------------|
| GET | `/api/admin/elections/<uuid>/turnout/` | EB Head, Operator, Tally Watcher, Auditor | Turnout statistics (eligible, voted, percentage, by-college). Available during Active/Closed/Published. **No candidate tallies.** |
| GET | `/api/admin/elections/<uuid>/tally/` | EB Head, Operator, Tally Watcher, Auditor | Full tally with candidate vote counts. **Blocked during Active** (returns 403). Available only after Close. |

### Modified Endpoints (Backward-Compatible)

| Endpoint | Change |
|----------|--------|
| `GET /api/elections/current/` | Now filters by student eligibility (voter roll) |
| `GET /api/elections/status/` | Now returns per-election status array alongside backward-compatible top-level fields |
| `GET /api/elections/results/` | Now requires eligibility check; uses `compute_results_with_thresholds` |
| `GET /api/elections/results/<uuid>/` | Same as above, for specific election |

---

## Key Design Decisions

1. **Eligibility-first filtering**: All student endpoints check `EligibleVoter` + college match before returning data. This is enforced server-side, not just UI-side.

2. **Multi-election support**: A student can be eligible for both a campus election and their college election simultaneously. `/api/elections/mine/` returns all of them.

3. **College isolation**: A student from College A cannot see, vote in, or view results for College B's election — even if accidentally added to the voter roll. The college match check runs at the view layer.

4. **No live candidate tallies**: The `turnout` endpoint only exposes aggregate counts (eligible, voted, percentage). The `tally` endpoint returns per-candidate vote counts but is **blocked during Active voting** (returns 403 with explicit message).

5. **50%+1 thresholds**: `compute_results_with_thresholds()` adds position-level threshold data. Denominator rules follow KNOWN_DECISIONS_COMPACT:
   - Campus positions → total campus voter roll
   - College election positions → that college election's voter roll
   - College Representatives in campus election → voters of the represented college

6. **Backward compatibility**: `current_election()` and `voting_status()` maintain their original response shapes while adding eligibility filtering internally.

7. **No model changes**: Bundle 04 introduces zero new models or migrations. All new behavior is in views, services, and templates.

---

## New Services

### `ResultService.compute_results_with_thresholds(election)`
Extends `compute_results()` with:
- `total_eligible`, `total_ballots`, `turnout_percentage` at top level
- `threshold_denominator`, `threshold_50_plus_1` per position

### `TurnoutService.compute_turnout(election)`
Returns:
- `total_eligible`, `total_voted`, `turnout_percentage`
- `by_college` breakdown (college name + eligible count)
- Does NOT expose per-candidate tallies

---

## Test Coverage (48 New Tests)

| Test Class | Count | What It Covers |
|------------|-------|----------------|
| `TestMyElections` | 8 | Dashboard eligibility, Active/Published filtering, has_voted flag, campus + college visibility |
| `TestCollegeIsolation` | 3 | Cross-college access denied, same-college access allowed |
| `TestElectionBallot` | 7 | Ballot structure, eligibility checks, inactive candidates excluded, has_voted flag |
| `TestResultsVisibility` | 7 | Active/Closed/Published rules, eligibility enforcement, threshold data, fallback results |
| `TestElectionTurnout` | 7 | Auth/role checks, turnout data, no candidate tallies, by-college breakdown |
| `TestElectionTallyReview` | 5 | Active blocked, Closed/Published available, Draft blocked |
| `TestMonitoringRoleEnforcement` | 5 | Tally Watcher, Auditor, Operator access; Technical Support denied |
| `TestTurnoutService` | 2 | Empty election, correct counts |
| `TestOneBallotPerElection` | 2 | Duplicate ballot rejected, different elections allowed |
| `TestComputeResultsWithThresholds` | 2 | Structure, turnout calculation |

---

## Frontend Changes

### Dashboard (`dashboard.html`)
- Calls `/api/elections/mine/` instead of `/api/elections/status/` + `/api/elections/current/`
- Renders per-election cards: Active elections show "Vote Now" button; Published show "View Results"
- Shows has_voted status per election ("Voted" / "Not Voted" / "Partially Voted")
- Displays election type label (Campus / College with college name)
- Right panel shows election count summary + student's college

### Ballot (`ballot.html`)
- Accepts `?election=<uuid>` query parameter from dashboard links
- Falls back to finding first active eligible election if no param
- Calls `/api/elections/<id>/ballot/` for election-specific ballot structure
- Handles `has_voted` response gracefully (shows already-voted alert)
- Error handling for 403/404 responses

### Results (`results.html`)
- Accepts `?election=<uuid>` query parameter
- Falls back to most recent published eligible election
- Added 4th stats card showing turnout percentage
- Position result cards now display 50%+1 threshold info
- Error handling for 403/404

---

## Regression Impact

- **7 existing tests** in `test_views.py` were updated to add `make_eligible()` calls, since the rewritten views now enforce voter roll eligibility. All 304 pre-existing tests pass without behavior changes.

---

## Final Metrics

| Metric | Value |
|--------|-------|
| Total tests | **352** (304 + 48 new) |
| All passing | **Yes** |
| Coverage | **90%** |
| New migrations | **0** |
| Regressions | **0** |
