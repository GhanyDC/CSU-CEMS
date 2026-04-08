# CEMS Manual Testing Checklist

Use this checklist to manually verify the full CEMS flow after a fresh setup or code change.

## Prerequisites

```bash
# 1. PostgreSQL running on localhost:5432
# 2. .env file configured (POSTGRES_HOST=localhost, etc.)
# 3. Virtual environment activated

# Apply migrations
python manage.py migrate --settings=config.settings.local

# Generate pilot data (admin users + students + election + voter roll)
python manage.py generate_pilot_data --clear --settings=config.settings.local

# Start the dev server
python manage.py runserver --settings=config.settings.local
```

---

## A. Automated Checks (run first)

| # | Command | Expected |
|---|---------|----------|
| A1 | `python -m pytest tests/ -v --tb=short` | 352+ tests pass |
| A2 | `python run_pilot_test.py` (with `DJANGO_SETTINGS_MODULE=config.settings.local`) | 59/59 checks pass |

---

## B. Student Auth Flow (Browser)

| # | Step | Expected |
|---|------|----------|
| B1 | Navigate to `http://localhost:8000/` | Login page loads |
| B2 | Enter invalid student_id / DOB | Error message, no redirect |
| B3 | Enter valid student credentials (see pilot data output) | Redirect to `/dashboard/` |
| B4 | Check dashboard shows "No elections" (election is DRAFT) | Empty election list |
| B5 | Click logout | Redirect to login page |

---

## C. Admin Auth Flow (Browser)

| # | Step | Expected |
|---|------|----------|
| C1 | Navigate to `http://localhost:8000/election-admin/login/` | Admin login page loads |
| C2 | Enter `eb_head` / `pilot_admin_pass` | Redirect to `/admin-panel/` |
| C3 | Admin panel shows election list with 1 DRAFT election | Election visible |
| C4 | Click the election row | Detail view with Overview, Candidates, Voter Roll, Readiness, Lifecycle tabs |

---

## D. Election Lifecycle (Admin Panel)

| # | Step | Expected |
|---|------|----------|
| D1 | In admin panel, click Readiness tab | Shows readiness check (positions, candidates, voter roll status) |
| D2 | Click Voter Roll tab | Shows 2000 eligible voters, finalized status |
| D3 | Click Lifecycle tab, click "Start Election" | Election transitions to ACTIVE, toast notification |
| D4 | Verify election list shows "Active" badge | Status badge is green |

---

## E. Student Voting (Browser - separate session)

| # | Step | Expected |
|---|------|----------|
| E1 | Login as a student | Dashboard now shows 1 active election |
| E2 | Click "Vote" on the election | Ballot page with 13 positions loads |
| E3 | Select candidates for each position | Selections highlight |
| E4 | Submit ballot | Success message, redirect to dashboard |
| E5 | Dashboard shows "Voted" badge for that election | has_voted = true |
| E6 | Try to access ballot again | "Already voted" message |

---

## F. Close & Publish (Admin Panel)

| # | Step | Expected |
|---|------|----------|
| F1 | In admin panel, Lifecycle tab, click "Close Election" | Election transitions to CLOSED |
| F2 | Click "Publish Results" | Election transitions to PUBLISHED |
| F3 | Verify no further transitions possible | Buttons disabled / no action |

---

## G. Results (Student Browser)

| # | Step | Expected |
|---|------|----------|
| G1 | Login as a student who voted | Dashboard shows PUBLISHED election |
| G2 | Click "View Results" | Results page shows positions with vote counts |
| G3 | Verify winner declared for executive positions | "Won" or "No Majority" status |

---

## H. API Spot Checks (curl or browser dev tools)

| # | Endpoint | Method | Expected |
|---|----------|--------|----------|
| H1 | `/api/elections/mine/` (authenticated student) | GET | List of eligible elections |
| H2 | `/api/elections/<uuid>/ballot/` (authenticated, active election) | GET | Ballot structure |
| H3 | `/api/admin/elections/setup/list/` (admin auth) | GET | Election list |
| H4 | `/api/admin/elections/<uuid>/turnout/` (admin auth, active+) | GET | Turnout stats |
| H5 | `/api/admin/elections/<uuid>/tally/` (admin auth, closed+) | GET | Full tally |

---

## I. Security Checks

| # | Check | Expected |
|---|-------|----------|
| I1 | Access `/api/elections/mine/` without login | 401 |
| I2 | Student accesses `/api/admin/elections/start/` | 401 |
| I3 | Operator admin calls lifecycle endpoint | 403 |
| I4 | 5+ failed login attempts | Account locked |
| I5 | Attempt double vote | 409 + audit log entry |
