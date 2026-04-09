# Manual Validation Checklist — Run 01

**Date:** 2026-04-09  
**Purpose:** Step-by-step manual testing to verify all fixes from the hardening run.

---

## Prerequisites

### Local Setup

```powershell
cd C:\Users\delac\CEMS
.venv\Scripts\Activate.ps1

# Apply migrations
python manage.py migrate --settings=config.settings.local

# Generate fresh pilot data (clears existing)
python manage.py generate_pilot_data --clear --settings=config.settings.local

# Start dev server
python manage.py runserver --settings=config.settings.local
```

### Pilot Data Credentials

| Role | Username | Password |
|------|----------|----------|
| Electoral Board Head | `eb_head` | `pilot_admin_pass` |
| Operator | `operator1` | `pilot_admin_pass` |
| Tally Watcher | `tally_watcher1` | `pilot_admin_pass` |
| Auditor | `auditor1` | `pilot_admin_pass` |
| Technical Support | `tech_support1` | `pilot_admin_pass` |

Student credentials are generated from pilot data. Check the console output of `generate_pilot_data` for student IDs and dates of birth.

---

## Test 1: Admin Login (Primary Fix Verification)

**What was broken:** Admin login form rendered but JavaScript was silently dropped. Clicking "Admin Sign In" did nothing.

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 1.1 | Open `http://localhost:8000/election-admin/login/` in an incognito window | Login page renders with amber/gold theme, "CEMS Election Admin" heading | |
| 1.2 | Right-click → View Page Source | Should see `<script>` block with `document.querySelector('form').addEventListener('submit', ...)` near the bottom of the page, inside the `extra_scripts` block | |
| 1.3 | Open browser DevTools → Console tab | No JavaScript errors | |
| 1.4 | Enter `eb_head` / `pilot_admin_pass` → click "Admin Sign In" | Redirected to `http://localhost:8000/admin-panel/` | |
| 1.5 | Admin panel loads with election list or "No elections created" | Page renders correctly, no errors in console | |

---

## Test 2: Admin Logout

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 2.1 | While logged in as admin, click the "Logout" button in the admin panel | Redirected to `/election-admin/login/` | |
| 2.2 | Navigate to `http://localhost:8000/admin-panel/` | Redirected back to `/election-admin/login/` (not authenticated) | |

---

## Test 3: Student Login

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 3.1 | Open `http://localhost:8000/login/` in a new incognito window | Student login page renders with blue theme | |
| 3.2 | View page source | Should see `{% csrf_token %}` rendered as a hidden input with `name="csrfmiddlewaretoken"` | |
| 3.3 | Enter a valid student ID and date of birth from pilot data | Redirected to `http://localhost:8000/dashboard/` | |
| 3.4 | Dashboard shows "Welcome" message and any active elections | Page renders correctly | |

---

## Test 4: Student Logout

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 4.1 | While logged in as student, click "Logout" | Redirected to `/login/` | |
| 4.2 | Navigate to `http://localhost:8000/dashboard/` | Redirected to `/login/` | |

---

## Test 5: Session Isolation

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 5.1 | In the SAME browser (not incognito), log in as a student at `/login/` | Dashboard loads | |
| 5.2 | Without logging out, navigate to `/election-admin/login/` and log in as `eb_head` | Admin panel loads | |
| 5.3 | Navigate back to `/dashboard/` | Should redirect to `/login/` (student session was cleared when admin logged in) | |
| 5.4 | Log out as admin | Returned to `/election-admin/login/` | |
| 5.5 | Log in as admin at `/election-admin/login/` | Admin panel loads | |
| 5.6 | Without logging out, log in as student at `/login/` | Dashboard loads | |
| 5.7 | Navigate to `/admin-panel/` | Should redirect to `/election-admin/login/` (admin session was cleared when student logged in) | |

---

## Test 6: Role Separation

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 6.1 | Log in as `operator1` at `/election-admin/login/` | Admin panel loads | |
| 6.2 | If an election exists in Draft state, try to click "Start Election" (or use DevTools to POST to `/api/election-admin/elections/{id}/start/`) | Should return 403 Forbidden (only EB Head can start) | |
| 6.3 | Log out. Log in as `tally_watcher1` | Admin panel loads | |
| 6.4 | Try to create an election (POST to `/api/election-admin/elections/create/`) | Should return 403 Forbidden | |
| 6.5 | Log out. Log in as `tech_support1` | Admin panel loads | |
| 6.6 | Try to access any operational endpoint (create election, list elections API, etc.) | Should return 403 Forbidden. Technical Support has no operational permissions. | |

---

## Test 7: Election Setup (EB Head)

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 7.1 | Log in as `eb_head` | Admin panel loads | |
| 7.2 | Create a new campus-wide election with a name and date range | Election created, appears in list with "Draft" status | |
| 7.3 | Click on the election to open detail view | Detail view loads with tabs: Overview, Positions, Candidates, Voter Roll, Readiness | |
| 7.4 | Add a position (e.g., "President") | Position appears in Positions tab | |
| 7.5 | Add at least 2 candidates to the position | Candidates appear in Candidates tab | |

---

## Test 8: Voter Roll Pipeline

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 8.1 | In the election detail, go to "Voter Roll" tab | Shows voter roll status (empty if not imported) | |
| 8.2 | Upload a verification CSV with student IDs and colleges | CSV processed, verification records created | |
| 8.3 | Run matching (if separate step) | Students matched against Student table | |
| 8.4 | Generate eligible voters | EligibleVoter records created | |
| 8.5 | Finalize voter roll | Voter roll locked; status changes to "Finalized" | |
| 8.6 | Try to upload another CSV after finalization | Should be rejected (voter roll is frozen) | |

---

## Test 9: Election Lifecycle

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 9.1 | With a fully set up election (positions, candidates, finalized voter roll), check Readiness tab | All checks should pass (green) | |
| 9.2 | Click "Start Election" | Election status changes to "Active" | |
| 9.3 | Try to add positions or candidates | Should be rejected (election is Active) | |
| 9.4 | Click "Close Election" | Election status changes to "Closed" | |
| 9.5 | Click "Publish Results" | Election status changes to "Published" | |
| 9.6 | Try to reopen or re-start the election | Should be rejected (Published is a terminal state) | |

---

## Test 10: Ballot Submission and Duplicate Prevention

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 10.1 | With an Active election, log in as an eligible student | Dashboard shows the election as available for voting | |
| 10.2 | Click on the election to view the ballot | Ballot page renders with positions and candidates | |
| 10.3 | Select candidates and submit the ballot | Success message; redirected to dashboard; election shows "Voted" | |
| 10.4 | Try to access the ballot page again for the same election | Should be blocked — student has already voted | |
| 10.5 | Using DevTools/curl, try to POST to the cast-ballot endpoint again | Should return 409 Conflict (duplicate ballot prevented) | |

---

## Test 11: Cross-College Isolation

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 11.1 | Create a college-specific election (e.g., for "College of Engineering") | Election created with college scope | |
| 11.2 | Log in as a student from a DIFFERENT college | Election should NOT appear in their dashboard | |
| 11.3 | Using DevTools, try to access the ballot page with the election UUID | Should return 403 or 404 (not eligible) | |

---

## Test 12: Results Visibility

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 12.1 | With an Active election, try to access results as a student | Should show "Results not available yet" or redirect | |
| 12.2 | Close the election (as EB Head) | Election is Closed | |
| 12.3 | Access results as a student | Depends on visibility setting — tally may be visible after Close or only after Publish | |
| 12.4 | Publish the election | Election is Published | |
| 12.5 | Access results as a student | Full results should be visible with vote counts | |

---

## Test 13: Wrong Credentials

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 13.1 | At `/election-admin/login/`, enter wrong password for `eb_head` | Error message "Invalid credentials" displayed; no redirect; no stack trace | |
| 13.2 | At `/login/`, enter invalid student ID | Error message displayed; no redirect | |
| 13.3 | At `/login/`, enter valid student ID with wrong DOB | Error message displayed | |

---

## Test 14: Anonymous Access Protection

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 14.1 | Without logging in, navigate to `/dashboard/` | Redirected to `/login/` | |
| 14.2 | Without logging in, navigate to `/admin-panel/` | Redirected to `/election-admin/login/` | |
| 14.3 | Without logging in, navigate to `/ballot/{any-uuid}/` | Redirected to `/login/` | |
| 14.4 | Without logging in, POST to `/api/voting/cast-ballot/` | Returns 403 or redirects to login | |
| 14.5 | Without logging in, navigate to `/login/` | Login page renders (200 OK) | |
| 14.6 | Without logging in, navigate to `/election-admin/login/` | Admin login page renders (200 OK) | |

---

## Test 15: Defensive Abuse-Case Checks

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 15.1 | POST to `/api/voting/cast-ballot/` with a non-existent election UUID | 404 Not Found or error message | |
| 15.2 | POST to `/api/voting/cast-ballot/` with a malformed UUID | 400 Bad Request or 404 | |
| 15.3 | POST with valid election but a candidate UUID from a different election | Rejected (candidate not in this election) | |
| 15.4 | POST with more candidates than `max_selections` for a position | Rejected with validation error | |

---

## Automated Test Suite Verification

```powershell
# Run full test suite (should be 424 tests, 0 failures)
python -m pytest tests/ -v --tb=short

# Run only the new hardening tests
python -m pytest tests/test_hardening.py -v --tb=short

# Run with coverage
python -m pytest tests/ --cov=apps --cov-report=term-missing
```

### Expected Results

| Metric | Expected |
|--------|----------|
| Total tests | 424 |
| Failures | 0 |
| Errors | 0 |
| New hardening tests | 67 |
| Original tests | 357 |
