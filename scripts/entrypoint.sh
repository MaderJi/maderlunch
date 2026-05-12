#!/usr/bin/env bash
set -euo pipefail

# Wenn als root gestartet, Volume-Permissions setzen und auf app-User wechseln
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/staticfiles 2>/dev/null || true
  exec gosu app "$0" "$@"
fi

echo "[entrypoint] waiting for db ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until python -c "import socket,os; s=socket.socket(); s.settimeout(2); s.connect((os.environ['POSTGRES_HOST'], int(os.environ['POSTGRES_PORT']))); s.close()" 2>/dev/null; do
  sleep 1
done
echo "[entrypoint] db reachable."

echo "[entrypoint] running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] collecting static files..."
python manage.py collectstatic --noinput

echo "[entrypoint] handing off to: $*"
exec "$@"
