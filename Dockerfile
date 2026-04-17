# ---------------------------------------------------------------------------
# CEMS – Dockerfile (production-grade, security-hardened)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Build stage — install Python deps
# ---------------------------------------------------------------------------
FROM base AS builder

WORKDIR /build
COPY requirements/ requirements/
ARG REQUIREMENTS_FILE=requirements/production.txt
RUN pip install --no-cache-dir --prefix=/install -r ${REQUIREMENTS_FILE}

# ---------------------------------------------------------------------------
# Runtime stage — non-root user
# ---------------------------------------------------------------------------
FROM base AS runtime

# Create non-root user
RUN groupadd -r cems && useradd -r -g cems -d /app -s /sbin/nologin cems

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . /app/

# Create required directories
RUN mkdir -p /app/staticfiles /app/logs /app/static \
    && chmod +x /app/docker/entrypoint.sh \
    && chown -R cems:cems /app

# Collect static files
RUN DJANGO_SECRET_KEY=build-placeholder \
    POSTGRES_PASSWORD=build-placeholder \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; hosts=[h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost').split(',') if h.strip() and h.strip() != '0.0.0.0']; host=next((h for h in hosts if h != '*'), 'localhost'); req=urllib.request.Request('http://127.0.0.1:8000/api/health/', headers={'Host': host, 'X-Forwarded-Proto': 'https'}); urllib.request.urlopen(req)" || exit 1

# Default: prepare writable runtime volumes, then run gunicorn as the cems user
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
