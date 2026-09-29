#!/bin/sh
# Apply database migrations, create the admin account if requested, then serve.
set -e

python manage.py migrate --noinput
python manage.py ensure_admin

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --access-logfile -
