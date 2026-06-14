#!/bin/sh
set -e

until pg_isready -h db -U postgres -d dev_dashboard; do
  echo "Waiting for postgres..."
  sleep 1
done

echo "Postgres is ready."

# If arguments are passed, execute them (e.g. Celery worker command)
if [ "$#" -gt 0 ]; then
  echo "Running custom command: $@"
  exec "$@"
fi

# Default: Run database migrations and start API
echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
