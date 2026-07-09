# CEMS Local Testing Guide

This guide explains how to test CEMS on your own machine before using it in a school facility or sharing it with other admins.

Run commands from the project root:

```powershell
cd C:\Users\delac\CEMS
```

## What You Need

- Python 3.12 recommended
- PostgreSQL, or Docker Desktop if you want Docker to run PostgreSQL for you
- Git
- Node.js, optional, only for checking frontend JavaScript syntax

The normal local app uses PostgreSQL. The automated Django test suite uses a temporary in-memory test database, so it will not modify your real voter/election data.

## First-Time Local Setup

Create your environment file:

```powershell
Copy-Item .env.example .env
```

For native local testing, edit `.env` and use values like:

```env
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=local-dev-secret-key-change-this-to-a-long-random-value
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DEBUG=True

POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=your-local-db-password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

For Docker local testing, use:

```env
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_HOST_PORT=5433
```

## Option A: Run Locally With Docker

This is the easiest option if you do not want to install PostgreSQL manually.

```powershell
docker compose up -d --build
docker compose ps
```

Open:

```text
http://localhost:8000
```

View logs:

```powershell
docker compose logs -f web
```

Stop the app:

```powershell
docker compose down
```

To delete only your local Docker test database and volumes, use this carefully:

```powershell
docker compose down -v
```

## Option B: Run Locally With Python

Use this if PostgreSQL is already installed and running locally.

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements\local.txt
```

Run migrations:

```powershell
python manage.py migrate
```

Create an admin login:

```powershell
python manage.py createsuperuser
```

Start the server:

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000
```

## Automated Smoke Checks

Run these before and after code changes.

If using the existing Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.elections --settings=config.settings.test
```

If your virtual environment is activated:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.elections --settings=config.settings.test
```

Expected results:

- `manage.py check` says `System check identified no issues`.
- `makemigrations --check --dry-run` says `No changes detected`.
- The election tests finish with `OK`.

## Production-Style Checks

These do not deploy the app. They check whether production settings can load cleanly.

```powershell
.\.venv\Scripts\python.exe manage.py check --deploy --settings=config.settings.production
.\.venv\Scripts\python.exe manage.py collectstatic --dry-run --noinput --settings=config.settings.production
```

Before running these, make sure `.env` has production-style required values such as `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and PostgreSQL settings.

## Frontend Syntax Check

If Node.js is installed, run this quick template script parser:

```powershell
$script = @'
const fs = require("fs");
const path = require("path");
const files = [
  "templates/frontend/admin_panel.html",
  "templates/frontend/dashboard.html",
  "templates/frontend/ballot.html",
  "templates/frontend/results.html",
  "templates/frontend/login.html",
  "templates/frontend/admin_login.html",
];
for (const file of files) {
  const html = fs.readFileSync(file, "utf8");
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)];
  scripts.forEach((match, index) => {
    new Function(match[1]);
  });
  console.log(`${path.basename(file)} scripts=${scripts.length}`);
}
'@
node -e $script
```

This only catches JavaScript syntax errors. It does not replace browser testing.

## Manual Browser Smoke Test

Start the app, then check these pages:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/dashboard/
http://127.0.0.1:8000/ballot/
http://127.0.0.1:8000/results/
http://127.0.0.1:8000/election-admin/login/
http://127.0.0.1:8000/admin-panel/
http://127.0.0.1:8000/api/health/
```

Expected behavior:

- `/api/health/` returns `{"status":"ok"}`.
- Student-only pages redirect to login when no student is logged in.
- Admin panel redirects to admin login when no admin is logged in.
- Login pages render without broken layout or console errors.

## College Election Workflow Test

Use this workflow for the next college election rehearsal.

1. Log in as an admin.
2. Create or activate the current school year.
3. Add enrollment records for at least two students from different colleges.
4. Create a draft college election for one college.
5. Link the election to the active school year.
6. Enable web voter registration.
7. Log in as a student from the same college.
8. Confirm the election appears under available registrations.
9. Register the student.
10. Confirm the admin registration summary shows the new eligible voter.
11. Log in as a student from a different college.
12. Confirm the other-college student cannot see or register for that college election.
13. Finalize the voter roll.
14. Start the election only after readiness checks pass.

Pass condition:

- Only enrolled students from the election college can register and vote.
- Other-college students are blocked even if they know the election URL.
- Voter roll finalization happens before the election starts.

## Campus College-Representative Test

Use this to verify the old issue does not return.

1. Create a campus election.
2. Add a campus-wide position such as President.
3. Add one House College Representative position per college.
4. Set each representative position's represented college correctly.
5. Add candidates whose college matches the represented college.
6. Add eligible voters from at least two different colleges.
7. Log in as a voter from College A.
8. Open the ballot.
9. Confirm the voter sees:
   - Campus-wide positions.
   - Only College A's representative position.
   - No representative positions or candidates from other colleges.
10. Cast a normal vote.
11. Try a tampered request or direct API vote using another college's representative candidate.

Pass condition:

- The ballot hides other-college representative seats.
- The server rejects cross-college representative votes.
- A valid same-college vote is recorded once.

## Election-Day Readiness Checklist

Before using the system for a real election:

- Run all automated smoke checks.
- Confirm the active school year is correct.
- Confirm enrollment records are current for the school year.
- Confirm every college election is linked to the correct college.
- Confirm campus representative positions have the correct represented college.
- Confirm candidates are active and assigned to the correct positions.
- Confirm registration is closed before finalizing the voter roll.
- Confirm voter roll counts match expectations.
- Confirm readiness checks pass before starting.
- Test one student login from each participating college.
- Test admin login for each admin role that will be used.
- Back up the database before opening voting.

## Troubleshooting

`DisallowedHost`

Update `DJANGO_ALLOWED_HOSTS` in `.env`.

CSRF errors

For local testing, use `http://127.0.0.1:8000` or `http://localhost:8000` consistently. For production-like testing, set `DJANGO_CSRF_TRUSTED_ORIGINS` to the exact HTTPS origin.

Database connection errors

Check `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. If using Docker, run:

```powershell
docker compose ps
docker compose logs db
```

Static files missing in production-style testing

Run:

```powershell
python manage.py collectstatic --noinput --settings=config.settings.production
```

Tests are noisy but pass

Local/test settings can print verbose debug output. The important result is the final `OK` or failure traceback.

Need a clean local database

Only do this on a local test database:

```powershell
python manage.py flush
```

For Docker local testing only:

```powershell
docker compose down -v
```
