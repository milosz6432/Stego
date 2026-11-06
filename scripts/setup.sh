#!/usr/bin/env bash
# One-time setup for STEGO LAB: Python venv + backend deps + frontend deps.
# Optional external tools are installed separately (see README / install-tools.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> STEGO LAB setup"

# ---- Backend -----------------------------------------------------------------
PY="${PYTHON:-python3}"
echo "==> Creating Python virtual environment (backend/.venv)"
"$PY" -m venv backend/.venv
# shellcheck disable=SC1091
source backend/.venv/bin/activate
python -m pip install --upgrade pip
echo "==> Installing backend requirements"
pip install -r backend/requirements.txt
deactivate

# ---- Frontend ----------------------------------------------------------------
if command -v npm >/dev/null 2>&1; then
  echo "==> Installing frontend dependencies"
  (cd frontend && npm install)
else
  echo "!! npm not found — install Node.js 18+ then run: (cd frontend && npm install)"
fi

echo
echo "==> Setup complete."
echo "   Start everything with:  ./scripts/start.sh"
echo "   Optional external tools: ./scripts/install-tools.sh  (or see README)"
