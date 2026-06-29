# CEMS On-Prem Deployment Guide

This guide is for school IT/admin teams deploying CEMS inside school facilities instead of a cloud host. It covers local testing, production setup, operating checks, backups, and handoff notes.

## Deployment Model

Recommended production setup:

- One Linux server or VM on the school network.
- Docker Compose runs PostgreSQL, Django/Gunicorn, and Nginx.
- Users access CEMS through a school DNS name such as `cems.school.edu` or an internal host such as `cems.local`.
- HTTPS is required for production because sessions, CSRF cookies, and voting workflows are security-sensitive.
- PostgreSQL data, media uploads, static output, and logs live in Docker volumes on the server.

Do not run production from a laptop, shared workstation, or personal account.

## Minimum Server Requirements

For pilot or college-level elections:

- 2 CPU cores
- 4 GB RAM
- 40 GB disk
- Ubuntu Server 22.04/24.04 LTS or similar Linux server
- Static IP address
- DNS record or reserved internal hostname
- UPS-backed power if possible

For campus-wide election day:

- 4 CPU cores
- 8 GB RAM
- 80+ GB disk
- Wired server connection
- Confirmed backup storage
- IT staff available during election opening and closing

## Required Software

For production server:

- Git
- Docker Engine
- Docker Compose plugin
- OpenSSL or school-issued TLS certificate tools

For local development without Docker:

- Python 3.12
- PostgreSQL 16
- Git
- Optional: Docker Desktop for running PostgreSQL locally

## Local Test First

Use this before pushing changes or before rehearsing a deployment.

### Option A: Local Docker

```bash
git clone https://github.com/GhanyDC/CSU-CEMS.git
cd CSU-CEMS
cp .env.example .env
```

Edit `.env` for local use:

```env
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DJANGO_CSRF_TRUSTED_ORIGINS=
DEBUG=True
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_PASSWORD=change-this-local-password
```

Start the local stack:

```bash
docker compose up -d --build
docker compose exec web python manage.py seed_colleges
docker compose exec web python manage.py create_admin --username eb_head --role electoral_board_head --display-name "Electoral Board Head"
```

Open:

- Student/admin login: `http://localhost:8000/`
- Admin panel: `http://localhost:8000/election-admin/login/`
- Health check: `http://localhost:8000/api/health/`

### Option B: Native Python

Use this when actively developing code.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements\local.txt
Copy-Item .env.example .env
```

Set `.env` to point to your PostgreSQL database:

```env
DJANGO_SETTINGS_MODULE=config.settings.local
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=your-local-db-password
```

Then run:

```powershell
python manage.py migrate
python manage.py seed_colleges
python manage.py create_admin --username eb_head --role electoral_board_head --display-name "Electoral Board Head"
python manage.py runserver
```

## Local Verification Commands

Run these before deploying:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.elections --settings=config.settings.test
```

If using Docker:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test apps.elections --settings=config.settings.test
```

Expected result:

- System check reports no issues.
- Makemigrations reports no changes.
- Election tests pass.

## Production Setup On School Server

### 1. Prepare Server Directory

```bash
sudo mkdir -p /opt/cems
sudo chown "$USER":"$USER" /opt/cems
cd /opt/cems
git clone https://github.com/GhanyDC/CSU-CEMS.git .
cp .env.example .env
```

### 2. Configure `.env`

Use real secrets and the school hostname:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=cems.school.edu
DJANGO_CSRF_TRUSTED_ORIGINS=https://cems.school.edu
DEBUG=False

POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=replace-with-strong-db-password
POSTGRES_HOST=db
POSTGRES_PORT=5432

GUNICORN_WORKERS=3
DJANGO_RUN_MIGRATIONS=1
DJANGO_COLLECTSTATIC=1
```

Generate a secret key with:

```bash
openssl rand -base64 48
```

Never commit `.env`.

### 3. Configure DNS And TLS

Point the DNS name to the server IP.

Edit `docker/nginx.conf` and replace the sample `server_name` values with the school hostname.

Place TLS files on the host:

```bash
sudo mkdir -p /opt/cems/certs
sudo cp fullchain.pem /opt/cems/certs/fullchain.pem
sudo cp privkey.pem /opt/cems/certs/privkey.pem
sudo chmod 600 /opt/cems/certs/privkey.pem
```

The current production compose file mounts `/opt/cems/certs` into Nginx.

If TLS is terminated by a school firewall or reverse proxy instead, update `docker/nginx.conf` and the firewall/proxy rules accordingly. Keep `X-Forwarded-Proto: https`.

### 4. Start Production

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Seed colleges and create the first admin:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py seed_colleges
docker compose -f docker-compose.prod.yml exec web python manage.py create_admin --username eb_head --role electoral_board_head --display-name "Electoral Board Head"
```

Check health:

```bash
curl -k https://cems.school.edu/api/health/
```

## Production Validation Checklist

Before announcing the system:

- Login page loads over HTTPS.
- Admin can log in.
- Colleges are seeded.
- Active school year exists.
- Enrolled students are in the school-year roster.
- Web registration can be enabled for a draft election.
- A student from the correct college can register for their own college election.
- A student from another college cannot register for that college election.
- Voter roll can be finalized.
- Election readiness passes before starting.
- `/api/health/` returns success.
- Backups are working and restorable.

## Election Operations Workflow

1. Create or activate a school year.
2. Add enrolled students to the roster.
3. Create campus or college elections.
4. Link the election to the active school year.
5. Enable web registration.
6. Let students register from their dashboard.
7. Review eligible voter counts.
8. Finalize the voter roll.
9. Run readiness check.
10. Start the election.
11. Close the election.
12. Publish results after verification.

Important college-election rule: only students with an active enrollment in the same college can register or vote in that college election.

## Updates And Rollback

Pull and rebuild:

```bash
cd /opt/cems
git pull origin master
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

Rollback to previous commit:

```bash
git log --oneline -5
git revert <commit_sha>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

For database-changing releases, take a backup before pulling.

## Backups

Create a backup directory:

```bash
mkdir -p /opt/cems/backups
```

Database backup:

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U cems -d cems > /opt/cems/backups/cems_$(date +%Y%m%d_%H%M).sql
```

Media backup:

```bash
docker run --rm -v cems_media_volume:/media -v /opt/cems/backups:/backup alpine tar czf /backup/cems_media_$(date +%Y%m%d_%H%M).tar.gz /media
```

Restore database to a clean database only:

```bash
cat /opt/cems/backups/cems_YYYYMMDD_HHMM.sql | docker compose -f docker-compose.prod.yml exec -T db psql -U cems -d cems
```

Keep at least:

- One backup before every election.
- One backup after voter-roll finalization.
- One backup after election close.
- One backup after results publication.

Store copies outside the server.

## Logs And Troubleshooting

View container status:

```bash
docker compose -f docker-compose.prod.yml ps
```

View app logs:

```bash
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f db
```

Common fixes:

- `DisallowedHost`: update `DJANGO_ALLOWED_HOSTS`.
- CSRF failures: update `DJANGO_CSRF_TRUSTED_ORIGINS` with the exact HTTPS origin.
- Login redirects to HTTP/HTTPS loop: verify reverse proxy sends `X-Forwarded-Proto: https`.
- Static files missing: run `collectstatic` and restart.
- Database connection errors: check `POSTGRES_*` values and `docker compose ps`.

## Repository Handoff Rules

Do not commit:

- `.env` or passwords
- `media/`
- `staticfiles/`
- `logs/`
- `.venv/`
- `_debug*.py`
- generated `docs/agent_outputs/`

Do commit:

- source code under `apps/`, `config/`, `templates/`, `static/`
- migrations
- curated documentation under `docs/`
- `requirements/`
- Docker and deployment configuration

## Final Pre-Election Checklist

- Server is on UPS or reliable power.
- DNS and HTTPS are working.
- Latest code is deployed.
- Database backup exists.
- Admin accounts are limited to authorized election staff.
- Student roster is current for the school year.
- Voter roll is finalized.
- Readiness check passes.
- IT has rollback and backup commands ready.
