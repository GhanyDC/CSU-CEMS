# Campus Election Management System (CEMS)

CEMS is a Django-based Campus Election Management System being built for Cagayan State University. The project is designed to support student authentication, election lifecycle management, ballot submission, audit logging, and results publication through both API endpoints and a simple web interface.

## Overview

The system currently covers the core election flow:

- Student login using student ID and date of birth
- Role-aware access for student voters and election administrators
- Election lifecycle management from draft to active, closed, and published
- Ballot casting with one-ballot-per-voter-per-election enforcement
- Published results viewing
- Audit logging for security-relevant events
- Django admin for managing election data

## Key Features

- Election model with positions and candidates
- Ballot-based voting flow with per-election voter hashing
- Database constraints to reduce duplicate ballot and selection issues
- Account lockout and rate limiting on login attempts
- Admin-only election start, close, and publish actions
- Web UI for login, dashboard, ballot, results, and admin controls
- Docker-based local development setup
- Automated test suite with pytest

## Tech Stack

- Python 3.12
- Django 5.1
- PostgreSQL 16
- Docker and Docker Compose
- pytest, pytest-django, pytest-cov

## Project Structure

```text
apps/
  accounts/     Student authentication, session handling, access decorators
  audit/        Audit logging models and services
  elections/    Election, position, candidate models and lifecycle/results APIs
  frontend/     Template-driven web interface
  voting/       Ballot models, ballot service, voting endpoint
config/
  settings/     Base, local, production, and test settings
static/         Frontend CSS and JavaScript
templates/      HTML templates for the web UI
tests/          Automated test suite
```

## Main Endpoints

### Authentication

- `POST /api/auth/login/`
- `POST /api/auth/logout/`

### Elections

- `GET /api/elections/current/`
- `GET /api/elections/status/`
- `GET /api/elections/results/`
- `GET /api/elections/results/<election_id>/`

### Voting

- `POST /api/voting/cast/`

### Admin Election Lifecycle

- `POST /api/admin/elections/start/`
- `POST /api/admin/elections/close/`
- `POST /api/admin/elections/publish/`

## Web Interface

When running locally, the project exposes a basic web UI with pages for:

- Login
- Dashboard
- Ballot
- Results
- Admin panel

## Local Development

### 1. Create your environment file

```powershell
Copy-Item .env.example .env
```

Update `.env` with your local secrets and database password.

### 2. Start the stack

```bash
docker compose up --build
```

The application will be available at:

- App: `http://127.0.0.1:8000/`
- Django Admin: `http://127.0.0.1:8000/admin/`

### 3. Apply migrations manually if needed

```bash
docker compose exec web python manage.py migrate
```

### 4. Create a Django superuser

```bash
docker compose exec web python manage.py createsuperuser
```

## Running Tests

```bash
pytest
```

If you are running tests outside Docker, use the test settings module:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.test"
pytest
```

## Environment Variables

The repository includes `.env.example` as a template. Important values include:

- `DJANGO_SECRET_KEY`
- `DJANGO_SETTINGS_MODULE`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

Do not commit a real `.env` file or any production credentials.

## Security Notes

- Student identifiers are not stored directly in ballot records
- Login attempts are rate-limited and audited
- Repeated failed logins trigger account lockout
- Election actions are restricted to admin users
- Results are intended to be viewed only after publication

## Status

This repository is an active university project for Cagayan State University and is still evolving. It already supports the main election workflow, but it should still be reviewed, tested, and hardened further before any high-stakes production deployment.
