#!/bin/sh
set -eu

mkdir -p /app/media /app/staticfiles /app/logs
chown -R cems:cems /app/media /app/staticfiles /app/logs
chmod -R ug+rwX /app/media /app/staticfiles /app/logs

if [ "$#" -gt 0 ]; then
    exec runuser -u cems -- "$@"
fi

if [ "${DJANGO_RUN_MIGRATIONS:-0}" = "1" ]; then
    runuser -u cems -- python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
    runuser -u cems -- python manage.py collectstatic --noinput
fi

exec runuser -u cems -- \
    gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
