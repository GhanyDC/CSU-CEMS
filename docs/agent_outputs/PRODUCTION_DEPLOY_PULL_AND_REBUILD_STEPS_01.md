# Production Deploy: Pull and Rebuild Steps

**Date:** 2026-04-18
**For:** Lightsail server deployment after pulling this commit

---

## Prerequisites

- SSH access to Lightsail instance
- Docker and Docker Compose installed
- `.env` file configured on the server with production values

---

## Step-by-Step Deployment

### 1. SSH into the server

```bash
ssh your-user@your-lightsail-ip
cd /path/to/cems
```

### 2. Pull latest changes

```bash
git pull origin master
```

### 3. Verify `.env` has all required variables

Your `.env` must include at minimum:

```env
DJANGO_SECRET_KEY=<a-real-secret-key-at-least-50-characters>
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_ALLOWED_HOSTS=your-domain.edu,your-ip-address
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.edu
POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_HOST=db
POSTGRES_PORT=5432
GUNICORN_WORKERS=3
DJANGO_RUN_MIGRATIONS=1
DJANGO_COLLECTSTATIC=1
```

### 4. Rebuild and restart

```bash
sudo docker compose -f docker-compose.prod.yml down
sudo docker compose -f docker-compose.prod.yml up -d --build
```

**Note:** `--build` is **required** for this deployment because dependency files (`requirements/base.txt`, `requirements/production.txt`) and settings (`config/settings/production.py`) were changed.

### 5. Monitor startup

```bash
# Watch logs for successful boot
docker compose -f docker-compose.prod.yml logs -f web

# Expected output should show:
# - Migrations applied (if any pending)
# - "X static files copied to '/app/staticfiles', Y unmodified, Z post-processed."
# - "Starting gunicorn ..."
# - "Listening at: http://0.0.0.0:8000"
# - "Booting worker with pid: ..."
```

Press `Ctrl+C` to stop following logs once you see Gunicorn workers booted.

### 6. Verify all containers are healthy

```bash
docker compose -f docker-compose.prod.yml ps
```

Expected: all 3 containers (db, web, nginx) show `Up` status, web shows `(healthy)`.

---

## Post-Deploy Smoke Checks

Run these from the server or any machine that can reach the domain:

```bash
# Health endpoint
curl -s https://your-domain.edu/api/health/
# Expected: {"status": "ok"}

# Student login page
curl -s -o /dev/null -w '%{http_code}' https://your-domain.edu/
# Expected: 200

# Admin login page
curl -s -o /dev/null -w '%{http_code}' https://your-domain.edu/election-admin/login/
# Expected: 200

# Static files
curl -s -o /dev/null -w '%{http_code}' https://your-domain.edu/static/css/cems.css
# Expected: 200
```

If the server does not have a domain/TLS yet, test with:

```bash
# From inside the web container
docker exec cems-web-1 python -c "
import urllib.request
headers = {'Host': 'your-allowed-host', 'X-Forwarded-Proto': 'https'}
req = urllib.request.Request('http://127.0.0.1:8000/api/health/', headers=headers)
r = urllib.request.urlopen(req)
print(r.status, r.read().decode())
"
```

---

## What This Deployment Changes

| What | Impact |
|------|--------|
| `requirements/production.txt` | Removed dead `django-secure` package. **Rebuild required.** |
| `requirements/base.txt` | Tightened `python-json-logger` floor to `>=3.0.0`. **Rebuild required.** |
| `config/settings/production.py` | Replaced deprecated `STATICFILES_STORAGE` with `STORAGES` dict. No data migration needed. |
| `.gitignore` | Allows `docs/agent_outputs/` to be tracked. No runtime impact. |

---

## Is a Rebuild Required?

**Yes.** Dependency files changed, so `docker compose up -d --build` is mandatory.

## Are Migrations Required?

**No new migrations.** The entrypoint runs `migrate --noinput` automatically when `DJANGO_RUN_MIGRATIONS=1` (default). No schema changes were introduced by these fixes.

## Is collectstatic Handled Automatically?

**Yes.** The entrypoint runs `collectstatic --noinput` when `DJANGO_COLLECTSTATIC=1` (default). Additionally, the Dockerfile runs collectstatic during image build.

---

## Rollback Plan

If the rebuild fails or the app doesn't boot:

```bash
# 1. Stop the broken deployment
docker compose -f docker-compose.prod.yml down

# 2. Revert to previous commit
git log --oneline -3   # find the previous commit hash
git checkout <previous-commit-hash>

# 3. Rebuild with the old code
docker compose -f docker-compose.prod.yml up -d --build

# 4. Verify
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs web --tail=20
```

**Important:** Do NOT use `docker compose down -v` for rollback — the `-v` flag deletes database volumes and you will lose all data.
