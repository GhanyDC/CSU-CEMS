# Latest Integration Local Test Guide 01

## Recommended local workflow

Use `docker compose` as the source-of-truth local run path for this repo.

- it matches the project stack in this repo (`Django + PostgreSQL + Docker`)
- the `web` service now runs migrations and static collection correctly on startup
- this path was verified end-to-end on April 17, 2026 against the running local stack

## Environment expectations

The local Compose file reads `.env`.

If you do not already have one:

1. copy `.env.example` to `.env`
2. set a real `DJANGO_SECRET_KEY`
3. keep `DJANGO_SETTINGS_MODULE=config.settings.local`
4. keep `POSTGRES_HOST=db`
5. keep `POSTGRES_PORT=5432`
6. use `POSTGRES_HOST_PORT=5433` unless you know `5432` is free on your machine

## Exact commands

### 1. Start local services

```powershell
docker compose up --build -d
```

### 2. Confirm both containers are healthy

```powershell
docker compose ps
```

Expected outcome:

- `db` is `healthy`
- `web` is `healthy`
- web is exposed on `0.0.0.0:8000`
- db is exposed on `0.0.0.0:5433` by default

### 3. Seed colleges

```powershell
docker compose exec web python manage.py seed_colleges
```

### 4. Generate demo admins, students, and the pilot election

```powershell
docker compose exec web python manage.py generate_pilot_data --clear --students 200
```

Expected seeded admin accounts:

- `eb_head / pilot_admin_pass`
- `operator1 / pilot_admin_pass`
- `tally_watcher1 / pilot_admin_pass`

### 5. Print one student login credential pair for ballot testing

```powershell
docker compose exec web python manage.py shell -c "from apps.accounts.models import Student; s=Student.objects.order_by('student_id').first(); print(f'{s.student_id},{s.date_of_birth.isoformat()}')"
```

Use the output as:

- username: `<student_id>`
- password/date-of-birth field: `<YYYY-MM-DD>`

### 6. Run the targeted regression suite

```powershell
docker compose exec web python manage.py test apps.elections --settings=config.settings.test
```

### 7. Optional migration drift check

```powershell
docker compose exec web python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

### 8. Optional host-side smoke checks

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/api/health/
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/election-admin/login/
```

Expected outcome:

- `/api/health/` returns `{"status":"ok"}`
- `/` returns `200`
- `/election-admin/login/` returns `200`

Do not use `http://localhost:8000/election-admin/`; that route is not defined and returns `404`.

## URLs to open

- Student login: `http://localhost:8000/`
- Admin login: `http://localhost:8000/election-admin/login/`
- Admin panel after login: `http://localhost:8000/admin-panel/`
- Student ballot page: `http://localhost:8000/ballot/`
- Student results page: `http://localhost:8000/results/`
- Health check: `http://localhost:8000/api/health/`

## Accounts and flows to test

### Admin side

1. Log in at `http://localhost:8000/election-admin/login/` as `eb_head`.
2. Open `AY 2025-2026 SSC General Election (Pilot)`.
3. Confirm the election is present in `draft`.
4. Confirm the admin tabs remain:
   `Overview`, `Positions & Candidates`, `Voter Roll`, `Lifecycle`
5. Confirm there is no permanent Monitoring tab.
6. Confirm there is no permanent Readiness tab.

Expected outcome:

- EB Head can view the election and manage lifecycle actions
- Operator and Tally Watcher accounts still authenticate normally
- role-based access stays intact

### Student side

1. Log in at `http://localhost:8000/` with the student credential from step 5.
2. Confirm the login succeeds.
3. If the election is still `draft`, expect no active election ballot yet.

Expected outcome:

- student login succeeds
- before the election is started, `/api/elections/current/` returns `No active election at this time.`

## Hybrid regression test flow

### A. Prepare a hybrid election

1. Log in as `eb_head`.
2. Open the pilot election.
3. In `Overview`, change `Voting Mode` from `Online` to `Hybrid`.
4. Start the election.

Expected outcome:

- the election starts normally
- admin tabs remain `Overview`, `Positions & Candidates`, `Voter Roll`, `Lifecycle`
- `Hybrid Canvass` appears only because the election is hybrid

### B. Optional online ballot test

1. Log in at `http://localhost:8000/` with the student credential from step 5.
2. Cast a ballot.
3. Confirm the ballot cannot be submitted twice.

Expected outcome:

- review/submit reflects the selected ballot state
- duplicate submission is blocked

### C. Close the election and test the hybrid gate

1. Go back to the admin panel as `eb_head`.
2. Close the election.
3. Open `Hybrid Canvass`.
4. Download the tally template from the UI.

Expected outcome:

- publish stays disabled until both hybrid imports are valid

### D. Upload roster A

Create a CSV named `hybrid_roster_a.csv` with valid student IDs that did not vote online:

```csv
student_id
<student_id_1>
<student_id_2>
```

Upload it in `Hybrid Canvass`.

Expected outcome:

- roster import succeeds
- hybrid summary shows onsite turnout rows
- publish is still disabled because tally is still missing

### E. Upload a valid tally

Use the downloaded tally template and keep every candidate row present.

Set `onsite_votes` so each position stays within:

- `onsite participants * max selections`

Examples:

- President, Governor, and other single-seat positions must total `<= onsite participants`
- Senate rows must total `<= onsite participants * 12`
- Party-list rows must total `<= onsite participants * 3`

Upload the edited file.

Expected outcome:

- tally import succeeds
- publish becomes enabled

### F. Re-upload roster B to verify the regression fix

Create a different roster file, for example:

```csv
student_id
<student_id_3>
```

Upload it after the valid tally is already active.

Expected outcome:

- roster import succeeds
- the previously active tally is cleared automatically
- hybrid status returns to `Waiting on Imports`
- publish becomes disabled again

This is the main hybrid regression that was fixed.

### G. Try an invalid over-limit tally

Use the downloaded template again, but intentionally make a single-seat position exceed the onsite participant count.

Example:

- onsite participants: `1`
- President candidate rows total: `2`

Upload that invalid file.

Expected outcome:

- import is rejected
- validation error mentions the tally exceeding the allowed maximum
- publish remains disabled

### H. Upload a corrected tally and publish

1. Upload a corrected tally file that stays within the allowed limits.
2. Publish the election.
3. Open `http://localhost:8000/results/` as an eligible student.

Expected outcome:

- publish succeeds only after a valid current roster and valid current tally both exist
- student results are visible only after `Published`
- hybrid student results stay combined-only and do not expose online or onsite split fields

## Non-Docker note

Automated tests can still run directly on the host with:

```powershell
python manage.py test apps.elections --settings=config.settings.test
```

For manual local verification, Docker Compose is the recommended path.
