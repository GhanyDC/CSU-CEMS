# STUDENT HARDENING RUN 01 — Output

**Run date:** 2026-04-10  
**Agent run:** Student-side hardening, responsive refinement, bug-fix, and alignment pass  
**Status:** COMPLETE — all objectives addressed, 539 tests passing (0 failures)

---

## Summary

This run performed a full inspection, planning, and implementation pass on the CEMS student-side flow. The primary focus was:

1. **Critical bug fix:** Review & Submit section not updating when candidates are selected
2. **Abstain card conversion:** Abstain is now a card, not a separate checkbox
3. **Single source of truth:** Ballot state refactored to use a centralized `ballotState` Map
4. **Responsive improvements:** Mobile-friendly layout for all student pages
5. **Hardening:** Error handling, session expiry, duplicate submission prevention
6. **Test coverage:** 41 new student hardening tests added (182 student-related tests total)

---

## Student-Side Issues Found

### Critical: Review/Submit Sync Bug

**Root cause:** In the original `handleSelection()` function, the DOM query `input[data-position-id="${posId}"]` matched **both** candidate inputs **and** the abstain checkbox. When the forEach loop reached the abstain input, `inp.closest('.candidate-card')` returned `null` (abstain was not inside a `.candidate-card`). The subsequent `card.classList.add('selected')` threw a `TypeError`, which **stopped execution** before `updateSummary()` was called.

**Effect:** Candidate card visual state updated correctly (processed before the abstain input in DOM order), but the counter badge and Review & Submit summary section never updated. This made it appear that selections were not reflected in the review.

**Fix applied:** Complete rewrite of ballot state management. The new approach uses a `ballotState` Map as the **single source of truth**. All UI interactions update the Map, and `syncUI()` renders all visual elements from that state—cards, counters, and summary. DOM queries are no longer used for state derivation.

### Secondary Issues Found and Fixed

| Issue | Fix Applied |
|-------|-------------|
| Abstain was a separate checkbox, visually inconsistent | Converted to a card in the same grid as candidates |
| No session expiry handling on ballot page | Added `showSessionExpired()` with redirect to login |
| No election-closed-during-voting handling | Added `showElectionClosed()` with user-friendly message |
| Submit button could be tapped multiple times | Disabled immediately on submit, shows spinner |
| 409 duplicate errors showed raw message | Now shows friendly message and redirects to dashboard |
| Success modal lacked election context | Added election name and submission timestamp |
| Results page no clear "not eligible" state | Added `results-not-eligible` alert panel |
| Candidate photo errors on results page | Added `onerror` fallback to placeholder |
| No keyboard support for candidate cards | Added Enter/Space key handlers |
| Review section not responsive on mobile | Added responsive CSS with stacking layout |
| Candidate cards too small on mobile | Improved column sizing and touch target spacing |
| Dashboard error handling too generic | Added session expiry detection with auto-redirect |

---

## Implementation Approach

### Ballot State Model

```
ballotState: Map<positionId, { candidates: Set<candidateId>, abstain: boolean }>
```

- **`selectCandidate(posId, candId)`** — Updates candidate set, clears abstain
  - Single-select: replaces existing selection (or toggles off)
  - Multi-select: toggles candidate, enforces max_selections limit
- **`toggleAbstain(posId)`** — Toggles abstain, clears all candidates if enabling
- **`syncUI()`** — Renders everything from state: card classes, abstain card, counters, summary
- **`updateSummary()`** — Builds review HTML from state, enables/disables submit button

### Submit Flow

1. Build `selections[]` from `ballotState` (candidates only, not abstain)
2. Validate at least one selection (all-abstain blocked)
3. Show confirm dialog
4. Disable button immediately + show spinner
5. POST to `/api/voting/cast/`
6. On success: show modal with election name + timestamp, hide form
7. On 409 (duplicate): show friendly message, auto-redirect to dashboard
8. On 401 (session expired): show session expiry banner
9. On other errors: show toast, re-enable button

---

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `templates/frontend/ballot.html` | **Major rewrite** | Complete JS rewrite with single source of truth state model, abstain card, enhanced error handling, keyboard accessibility |
| `templates/frontend/results.html` | **Enhancement** | Added not-eligible state, photo fallbacks, session expiry handling, responsive improvements |
| `templates/frontend/dashboard.html` | **Enhancement** | Added session expiry detection with auto-redirect |
| `static/css/cems.css` | **Enhancement** | Added abstain card styles, review section styles, enhanced mobile responsive breakpoints, session expiry banner |
| `tests/test_student_hardening.py` | **New file** | 41 new tests covering page rendering, state validation, submit hardening, college rep filtering, isolation, results, dashboard eligibility, multi-position ballots |

---

## Migrations

No new migrations were added or required. All changes are frontend-only (templates, CSS, JS) and tests.

---

## Tests Added/Updated

### New: `tests/test_student_hardening.py` — 41 tests

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestStudentPageRendering` | 8 | Anonymous redirect, authenticated rendering, viewport meta |
| `TestBallotStateValidation` | 7 | Draft/Closed/Published blocked, Active allowed, has_voted flag, invalid IDs |
| `TestVoteSubmissionHardening` | 7 | Duplicate 409, empty rejected, invalid candidate/position, max selections, closed election, no eligibility |
| `TestCollegeRepFiltering` | 3 | Own college only, position hidden if no candidates, campus-wide shown |
| `TestCrossCollegeIsolation` | 2 | Cannot vote in other college, not in mine list |
| `TestResultsHardening` | 5 | Blocked before publish, blocked for ineligible, available when published, turnout data present, 401 for anonymous |
| `TestDashboardEligibility` | 5 | Empty dashboard, draft/closed hidden, active+published shown, has_voted flag |
| `TestMultiPositionBallot` | 4 | Multi-position, multi-select, partial ballot, duplicate candidate rejected |

### Full Suite

- **539 tests passing** (0 failures)
- Previous: 498 tests → Added 41 new tests
- No regressions in any existing test

---

## Hardening Fixes Applied

1. **Ballot state single source of truth** — eliminates DOM-based state derivation bugs
2. **Abstain as card** — uniform visual treatment, consistent mutual exclusivity
3. **Submit double-tap prevention** — disabled immediately, spinner shown
4. **Session expiry handling** — detected on 401, shows banner with login link
5. **Election-closed-during-voting** — friendly message when election is no longer active
6. **409 duplicate handling** — user-friendly message + auto-redirect
7. **Keyboard accessibility** — Enter/Space support for card selection
8. **Photo fallback** — graceful degradation when candidate photos fail to load
9. **Results empty states** — distinct "not available" vs "not eligible" messages

---

## Responsive/Mobile Improvements

1. **Candidate cards** — col-6 on mobile (2 per row), touch-friendly sizing
2. **Abstain card** — same responsive grid as candidates
3. **Review section** — stacks vertically on mobile (label above value)
4. **Position headers** — wrap on small screens
5. **Submit button** — full width on mobile
6. **Results page** — name/votes stack vertically on mobile
7. **Dashboard** — election cards stack, metrics adapt
8. **Navbar** — text labels hidden on small screens (icons only)
9. **No horizontal scroll** on any student page at 320px viewport

---

## Commands to Run Locally

```bash
# Run full test suite
python -m pytest tests/ -q --tb=short

# Run just student hardening tests
python -m pytest tests/test_student_hardening.py -v

# Collect static files (for CSS changes)
python manage.py collectstatic --noinput

# Start dev server for manual testing
python manage.py runserver
```

---

## Remaining Follow-Ups

| Priority | Item | Notes |
|----------|------|-------|
| Low | Confirmation modal could replace native `confirm()` | Current native dialog works but isn't styled |
| Low | Add aria-live region for dynamic summary updates | Screen reader improvement |
| Low | Consider service worker for offline resilience | Would help with network interruptions during voting |
| Low | Results page election selector | Currently only shows first published; could offer dropdown for multiple |
| Low | Timer refresh on ballot page | Could warn when election is about to close |
| Info | No backend changes needed | All fixes were frontend-only; backend rules remain frozen |

---

## Frozen Rules Verified

All frozen rules from SYSTEM_SOURCE_OF_TRUTH remain enforced:

- ✅ Campus + College only
- ✅ Official voter roll = registrar import ∩ verification
- ✅ Separate admin auth from student auth
- ✅ VP/EB Head controls lifecycle and voter roll finalization
- ✅ College elections simultaneous
- ✅ No student access to live tallies during Active
- ✅ No system-side candidate qualification logic
- ✅ No UUID typing required in normal flows
- ✅ One ballot per student per election
- ✅ College representative filtering backend-enforced
