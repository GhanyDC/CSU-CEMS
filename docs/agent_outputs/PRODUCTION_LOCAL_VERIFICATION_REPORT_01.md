# Production Local Verification Report

**Date:** 2026-04-18

---

## Validation Summary

| Check | Result | Notes |
|-------|--------|-------|
| Production settings import | **PASS** | `django.setup()` with `config.settings.production` succeeds |
| `django manage.py check --deploy` | **PASS** | 0 issues (0 silenced) |
| Docker image build | **PASS** | Image `cems-prod-test` built (588 MB) |
| WhiteNoise available in container | **PASS** | `import whitenoise` succeeds |
| python-json-logger available in container | **PASS** | `from pythonjsonlogger.json import JsonFormatter` succeeds |
| Django version in container | **PASS** | Django 5.1.15 |
| Docker Compose config validation | **PASS** | `docker compose -f docker-compose.prod.yml config` succeeds |
| Full production stack boot | **PASS** | db (healthy), web (healthy), nginx (running) |
| Migrations run | **PASS** | All 20 migrations applied successfully |
| collectstatic | **PASS** | 135 unmodified, 372 post-processed files |
| Gunicorn startup | **PASS** | 3 workers booted, listening on 0.0.0.0:8000 |
| Health endpoint (inside container) | **PASS** | `200 {"status": "ok"}` |
| Health endpoint (via Nginx) | **PASS** | `{"status": "ok"}` via wget inside nginx container |
| Student login page (`/`) | **PASS** | HTTP 200, 18925 bytes content |
| Admin login page (`/election-admin/login/`) | **PASS** | HTTP 200, 8437 bytes content |
| Static files via Nginx | **PASS** | `/static/css/cems.css` → 200, 53127 bytes, with Cache-Control headers |
| No restart-loop | **PASS** | Container stayed healthy through full lifecycle |
| Migration drift check | **PASS** | `makemigrations --check --dry-run` → "No changes detected" |
| Docker HEALTHCHECK | **PASS** | Container reported `(healthy)` in `docker compose ps` |

---

## Exact Validation Commands Run

```bash
# 1. Production settings load test
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY=test-key-50-chars... \
POSTGRES_PASSWORD=check-placeholder \
DJANGO_ALLOWED_HOSTS=localhost \
DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost \
python -c "import django; django.setup(); print('OK')"

# 2. Django deploy checks
python manage.py check --deploy

# 3. Migration drift check
python manage.py makemigrations --check --dry-run

# 4. Docker image build
docker build --no-cache --build-arg REQUIREMENTS_FILE=requirements/production.txt -t cems-prod-test .

# 5. Package verification inside container
docker run --rm cems-prod-test python -c "import whitenoise; print('OK'); from pythonjsonlogger.json import JsonFormatter; print('OK')"

# 6. Django checks inside container
docker run --rm -e DJANGO_SECRET_KEY=... -e POSTGRES_PASSWORD=... -e DJANGO_ALLOWED_HOSTS=localhost \
  -e DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost -e DJANGO_SETTINGS_MODULE=config.settings.production \
  cems-prod-test python manage.py check --deploy

# 7. Docker Compose config validation
docker compose -f docker-compose.prod.yml config

# 8. Full stack boot
docker compose -f docker-compose.prod.yml up -d --build

# 9. Container status check
docker compose -f docker-compose.prod.yml ps

# 10. Web container logs
docker compose -f docker-compose.prod.yml logs web --tail=30

# 11. Health endpoint (inside web container)
docker exec cems-web-1 python -c "
import urllib.request
req = urllib.request.Request('http://127.0.0.1:8000/api/health/',
    headers={'Host': 'localhost', 'X-Forwarded-Proto': 'https'})
r = urllib.request.urlopen(req)
print(r.status, r.read().decode())
"

# 12. All critical pages (inside web container)
docker exec cems-web-1 python -c "
import urllib.request
headers = {'Host': 'localhost', 'X-Forwarded-Proto': 'https'}
# Student login
req = urllib.request.Request('http://127.0.0.1:8000/', headers=headers)
r = urllib.request.urlopen(req)
print('Student login:', r.status, len(r.read()))
# Admin login
req2 = urllib.request.Request('http://127.0.0.1:8000/election-admin/login/', headers=headers)
r2 = urllib.request.urlopen(req2)
print('Admin login:', r2.status, len(r2.read()))
"

# 13. Health via Nginx
docker exec cems-nginx-1 wget -q -O - --header="Host: localhost" --header="X-Forwarded-Proto: https" http://127.0.0.1/api/health/

# 14. Static files via Nginx
docker exec cems-nginx-1 wget -q -S -O /dev/null http://127.0.0.1/static/css/cems.css

# 15. Teardown
docker compose -f docker-compose.prod.yml down -v
```

---

## Remaining Caveats

1. **Host-level HTTP requests to `localhost:80` failed** — This is a Docker Desktop for Windows networking limitation. Inside-container tests confirmed full Nginx→Gunicorn connectivity works correctly. On Lightsail (native Docker), this will not be an issue.

2. **HTTPS redirect behavior** — `SECURE_SSL_REDIRECT=True` causes Django to redirect HTTP→HTTPS. The health check and Nginx config correctly use `X-Forwarded-Proto: https` to prevent redirect loops. In production behind a load balancer that terminates TLS, this works correctly.

3. **No load/stress testing performed** — This verification covers functional correctness only. Production load testing should be done separately.
