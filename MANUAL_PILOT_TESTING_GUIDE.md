# CEMS Manual Pilot Testing Guide

This guide is for running the current local CEMS project and performing a full manual pilot test from a clean baseline.

## Current Prepared State

The local database has already been prepared in this workspace with these conditions:

- Migrations are applied.
- Fresh pilot data was generated with `generate_pilot_data --clear`.
- The pilot election was reset to `draft`.
- The election time window was set to a valid range.
- The first seeded student was promoted to in-app admin.

Current election:

- Election ID: `27af0466-9749-47aa-91de-a1b7fa7aa964`
- Name: `AY 2025-2026 SSC General Election (Pilot)`
- Status: `draft`

Current pilot accounts:

- Admin: `2024-10029` / `2004-10-28` / `Rosario Ramos`
- Voter 1: `2024-10141` / `2002-10-13` / `Bryan Castillo`
- Voter 2: `2024-10154` / `2005-02-05` / `Rosa Soriano`
- Voter 3: `2024-10189` / `2003-07-14` / `Eduardo Del Rosario`

## What You Need Open

Use two PowerShell windows.

Window 1:

- Runs the Django server and stays open the whole time.

Window 2:

- Used for browser testing, optional API checks, and reset commands.

## 1. Start the Project

In Window 1:

```powershell
cd C:\Users\delac\CEMS
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=config.settings.local
```

When startup succeeds, Django should report that the development server is running at:

```text
http://127.0.0.1:8000/
```

Open these pages in your browser:

- App login: `http://127.0.0.1:8000/`
- Dashboard: `http://127.0.0.1:8000/dashboard/`
- Ballot: `http://127.0.0.1:8000/ballot/`
- Results: `http://127.0.0.1:8000/results/`
- Admin panel: `http://127.0.0.1:8000/admin-panel/`
- Django admin: `http://127.0.0.1:8000/admin/`

## 2. Baseline Manual Test Flow

### Phase A: Verify the Draft Starting State

Before logging in:

- Visit `http://127.0.0.1:8000/`.
- Confirm the login page renders.
- Try opening `http://127.0.0.1:8000/dashboard/` directly.
- Confirm unauthenticated users are redirected or blocked.

After logging in as a regular voter:

- Use Voter 1 credentials.
- Confirm the dashboard shows no active election yet, because the election starts in `draft`.
- Confirm the voter cannot access admin actions.

### Phase B: Verify Admin Access

Log out, then log in as the admin account:

- Student ID: `2024-10029`
- Date of birth: `2004-10-28`

Confirm:

- The dashboard loads successfully.
- Admin-only actions are visible.
- `Admin Panel` is usable.

### Phase C: Start the Election

While logged in as admin:

1. Open `http://127.0.0.1:8000/admin-panel/`.
2. Start the pilot election.
3. Confirm the election moves from `draft` to `active`.

Expected checks:

- Dashboard should now show an active election.
- Voters should now be able to access the ballot.
- Results should still not be public.

### Phase D: Cast the First Manual Ballot

Open an incognito/private browser window and log in as Voter 1:

- Student ID: `2024-10141`
- Date of birth: `2002-10-13`

Test the ballot flow:

1. Open the dashboard.
2. Open the ballot page.
3. Select one candidate for `President`.
4. Select one candidate for `Vice President`.
5. Select several candidates for `Senator`.
6. Submit the ballot.

Expected checks:

- Submission succeeds.
- The UI confirms the ballot was recorded.
- The voter is marked as having voted.
- Returning to the ballot should not allow a second valid submission.

### Phase E: Double-Vote Prevention

Still as Voter 1:

1. Try to submit another ballot.
2. Confirm the system rejects the second attempt.

Expected checks:

- No second successful submission is accepted.
- The voter remains marked as already voted.

### Phase F: Cast a Different Ballot as a Second Voter

Open another incognito/private browser window and log in as Voter 2:

- Student ID: `2024-10154`
- Date of birth: `2005-02-05`

Test:

1. Open the ballot page.
2. Choose a different set of candidates from Voter 1 where possible.
3. Submit the ballot.

Expected checks:

- Submission succeeds.
- This voter can vote normally.
- Vote tallies should differ once results are published.

### Phase G: Close the Election

Go back to the admin session and:

1. Open `Admin Panel`.
2. Close the election.

Expected checks:

- Election status changes from `active` to `closed`.
- No new ballots should be accepted after closing.

### Phase H: Verify Voting is Blocked After Close

Use Voter 3 in a fresh incognito/private session:

- Student ID: `2024-10189`
- Date of birth: `2003-07-14`

Test:

1. Log in.
2. Attempt to access the ballot and vote.

Expected checks:

- Voting is rejected because the election is closed.

### Phase I: Publish Results

Return to the admin session and:

1. Open `Admin Panel`.
2. Publish the results.

Expected checks:

- Election status changes from `closed` to `published`.
- Results page becomes accessible to voters.

### Phase J: Verify Results Visibility

Using any voter session:

1. Open `http://127.0.0.1:8000/results/`.
2. Confirm published results are visible.
3. Check that vote totals and winners appear per position.

Expected checks:

- Positions are listed.
- Candidates show vote counts.
- Winners can be inferred from the displayed tallies.

## 3. Recommended Evidence to Record During Testing

Capture these as screenshots or notes:

- Login page before authentication
- Voter dashboard while election is still `draft`
- Admin panel before start
- Admin panel after start
- Ballot page before submission
- Successful vote confirmation
- Rejected second vote
- Admin panel after close
- Rejected vote after close
- Results page after publish

## 4. Optional API Spot Checks

These are optional if you want to confirm backend behavior directly.

### Login

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login/" `
  -Method POST `
  -ContentType "application/json" `
  -SessionVariable session `
  -Body '{"student_id":"2024-10141","date_of_birth":"2002-10-13"}'
```

### Current election

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/elections/current/" `
  -WebSession $session
```

### Election status

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/elections/status/" `
  -WebSession $session
```

## 5. Reset Back to a Fresh Manual-Testing State

If you want to restart the pilot from scratch again, run this in Window 2 while the server is stopped:

```powershell
cd C:\Users\delac\CEMS
.venv\Scripts\python.exe manage.py generate_pilot_data --clear --settings=config.settings.local
```

Then re-apply the admin assignment and election reset:

```powershell
.venv\Scripts\python.exe manage.py shell --settings=config.settings.local -c "from django.utils import timezone; from datetime import timedelta; from apps.accounts.models import Student; from apps.elections.models import Election; Student.objects.update(is_admin=False, failed_attempts=0, lock_until=None); admin = Student.objects.order_by('student_id').first(); admin.is_admin = True; admin.save(update_fields=['is_admin']); election = Election.objects.first(); election.status='draft'; election.start_time = timezone.now() - timedelta(hours=1); election.end_time = timezone.now() + timedelta(days=3); election.save(update_fields=['status','start_time','end_time']); print(admin.student_id, admin.date_of_birth, election.id, election.status)"
```

After that, start the server again with:

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=config.settings.local
```

## 6. Stop the Project

In the PowerShell window running Django, press `Ctrl+C`.

## 7. Notes

- Local PostgreSQL on `localhost:5432` was reachable when this guide was prepared.
- The guide uses the current seeded dataset from April 8, 2026 in this workspace.
- If you regenerate pilot data again, the student accounts and candidates will change.
