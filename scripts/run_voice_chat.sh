#!/usr/bin/env bash
# CityNerve Reporting Line — standalone voice call UI. Not part of Streamlit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
PYTHON="${ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi
exec "$PYTHON" agent/harness/voice_bot.py "$@"
