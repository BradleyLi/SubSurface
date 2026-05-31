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

prepend_ld_library_path() {
  local dir="$1"
  if [ -d "$dir" ]; then
    case ":${LD_LIBRARY_PATH:-}:" in
      *":$dir:"*) ;;
      *) export LD_LIBRARY_PATH="$dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
    esac
  fi
}

prepend_ld_library_path "$ROOT/.build/ctranslate2-cuda/install/lib"
prepend_ld_library_path "/usr/local/cuda/lib64"

CUDNN_LIB_DIR="$("$PYTHON" - <<'PY' 2>/dev/null || true
import importlib

try:
    cudnn_lib = importlib.import_module("nvidia.cudnn.lib")
except Exception:
    raise SystemExit

paths = list(getattr(cudnn_lib, "__path__", []))
if paths:
    print(paths[0])
PY
)"
prepend_ld_library_path "$CUDNN_LIB_DIR"

export VOICE_CHAT_HOST="${VOICE_CHAT_HOST:-0.0.0.0}"

exec "$PYTHON" agent/harness/voice_bot.py "$@"
