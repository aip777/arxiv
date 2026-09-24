#!/bin/sh
set -e

# The compose healthcheck already waits for Postgres, so migrations can run straight away.
python manage.py migrate --noinput

exec "$@"
