#!/bin/sh
set -e

# Creates the SQLite database on first start and applies any new migrations.
python manage.py migrate --noinput

exec "$@"
