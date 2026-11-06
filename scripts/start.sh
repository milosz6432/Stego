#!/usr/bin/env bash
# Start STEGO LAB: FastAPI backend (:8000) + Vite frontend (:5173).
# Ctrl-C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${STEGO_BACKEND_PORT:-8000}"
FRONTEND_PORT="${STEGO_FRONTEND_PORT:-5173}"

if [ ! -d backend/.venv ]; then
  echo "!! backend/.venv missing — run ./scripts/setup.sh first"
  exit 1
fi

# Put a gem-installed zsteg on PATH if present (rbenv installs it off-PATH).
for d in /opt/rbenv/versions/*/bin "$HOME/.gem/ruby/"*/bin; do
  [ -x "$d/zsteg" ] && export PATH="$d:$PATH"
done

# shellcheck disable=SC1091
source backend/.venv/bin/activate

echo "==> Backend  : http://127.0.0.1:${BACKEND_PORT}  (API docs: /docs)"
( cd backend && exec uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" ) &
BACK_PID=$!

echo "==> Frontend : http://127.0.0.1:${FRONTEND_PORT}"
( cd frontend && STEGO_BACKEND="http://127.0.0.1:${BACKEND_PORT}" exec npm run dev -- --port "${FRONTEND_PORT}" ) &
FRONT_PID=$!

cleanup() {
  echo; echo "==> Shutting down…"
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo
echo "==> STEGO LAB is running. Open http://127.0.0.1:${FRONTEND_PORT}"
echo "    Press Ctrl-C to stop."
wait
