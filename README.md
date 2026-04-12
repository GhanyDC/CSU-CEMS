# Campus Election Management System

This repository contains a Django-based Campus Election Management System (CEMS) for managing student elections, ballot casting, audit logging, and published results.

## Stack

- Python 3.12
- Django
- PostgreSQL
- Docker and Docker Compose
- Nginx for production deployment

## Project Layout

```text
apps/
  accounts/    Authentication, roles, student/admin access
  audit/       Audit log models and services
  elections/   Election setup, lifecycle, results, exports
  frontend/    Template-based web interface
  voting/      Ballot models, voting flow, vote submission
config/
  settings/    Base, local, production, and test settings
docker/        Nginx configuration
requirements/  Python dependency sets
static/        CSS, JS, and image assets
templates/     HTML templates
```

## Core Features

- Student login flow
- Admin election management
- Election lifecycle controls
- Candidate and position management
- Ballot casting and results publication
- Audit logging
- Docker-based deployment

## Quick Start

1. Copy the environment template:

```powershell
Copy-Item .env.example .env
```

2. Update `.env` with real values.

3. Start the production-style stack:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. Run migrations if needed:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

## Important Environment Variables

- `DJANGO_SECRET_KEY`
- `DJANGO_SETTINGS_MODULE`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `GUNICORN_WORKERS`

Use `.env.example` as the template and do not commit real secrets.
