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
RUN pip install --no-cache-dir --prefix=/install -r requirements/local.txt

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
    && chown -R cems:cems /app

# Collect static files
RUN DJANGO_SECRET_KEY=build-placeholder \
    POSTGRES_PASSWORD=build-placeholder \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    python manage.py collectstatic --noinput 2>/dev/null || true

# Switch to non-root user
USER cems

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/admin/')" || exit 1

# Default: run with gunicorn
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
