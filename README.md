# Campus Election Management System (CEMS)

A production-grade, security-hardened campus election management system built with Django.

## Security Priorities
- **Integrity**: Transactional vote creation with database-level locking
- **Auditability**: Every security event logged to immutable audit table + structured log files
- **One-person-one-vote**: Enforced via `SELECT FOR UPDATE` + hashed student ID in votes
- **Strong authentication**: Student ID + DOB with account locking and rate limiting
- **Secure data storage**: No raw student IDs in vote records; all secrets via environment

## Quick Start (Local Development)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your values

# 2. Build and start
docker-compose up --build

# 3. Run migrations (auto-runs via docker-compose, or manually)
docker-compose exec web python manage.py migrate

# 4. Create superuser
docker-compose exec web python manage.py createsuperuser

# 5. Access
# App:   http://localhost:8000
# Admin: http://localhost:8000/admin/
```

## Running Tests

```bash
docker-compose exec web pytest
```

## Project Structure

```
cems/
├── config/
│   ├── settings/
│   │   ├── base.py          # Shared, security-hardened defaults
│   │   ├── local.py         # Local dev overrides (DEBUG=True)
│   │   └── production.py    # Production settings
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/            # Student model + authentication
│   ├── elections/           # Candidate model
│   ├── voting/              # Vote model + transactional service
│   └── audit/               # Immutable audit log
├── tests/                   # pytest test suite
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   └── production.txt
├── docker/
│   └── nginx.conf
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── pytest.ini
├── pyproject.toml
└── .pre-commit-config.yaml
```

## Tech Stack
- **Backend**: Django 5.1 LTS
- **Database**: PostgreSQL 16
- **Server**: Gunicorn + Nginx
- **Containerization**: Docker + docker-compose
- **Testing**: pytest + pytest-django
- **Code quality**: Black, isort, flake8, mypy, pre-commit
