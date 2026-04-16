#!/bin/sh
set -eu

mkdir -p /app/media /app/staticfiles /app/logs
chown -R cems:cems /app/media /app/staticfiles /app/logs
chmod -R ug+rwX /app/media /app/staticfiles /app/logs

exec su -s /bin/sh cems -c "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 120 --access-logfile - --error-logfile -"
