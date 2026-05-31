#!/usr/bin/env bash
# CityNerve full demo stack: dual Ollama, FastAPI, Streamlit, Voice Reporting Line.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

prepend_ld_library_path() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
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

OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
OLLAMA_MODELS="${OLLAMA_MODELS:-${HOME}/.ollama/models}"
export OLLAMA_MODELS
STREAMLIT_HOST="${STREAMLIT_HOST:-0.0.0.0}"
VOICE_CHAT_HOST="${VOICE_CHAT_HOST:-0.0.0.0}"

# Static app ports. Edit these defaults, or override per run:
#   FASTAPI_PORT=8000 STREAMLIT_PORT=8501 VOICE_CHAT_PORT=8503 ./scripts/run_citynerve.sh
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
VOICE_CHAT_PORT="${VOICE_CHAT_PORT:-8503}"
export FASTAPI_PORT STREAMLIT_PORT VOICE_CHAT_PORT

port_in_use() {
  local port="$1"
  "$PYTHON" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("0.0.0.0", port))
except OSError:
    raise SystemExit(0)
finally:
    sock.close()

raise SystemExit(1)
PY
}

PID_W1=""
PID_W2=""
STARTED_W1=0
STARTED_W2=0
PID_UVICORN=""
PID_STREAMLIT=""
PID_VOICE=""

port_listening() {
  local port="$1"
  port_in_use "$port"
}

require_port_available() {
  local port="$1"
  local label="$2"

  if port_listening "${port}"; then
    echo "ERROR: configured ${label} port :${port} is already in use." >&2
    echo "Set ${label}_PORT to a free static port, or run '$0 --stop' to stop known services." >&2
    exit 1
  fi
}

require_distinct_ports() {
  if [[ "${FASTAPI_PORT}" == "${STREAMLIT_PORT}" \
      || "${FASTAPI_PORT}" == "${VOICE_CHAT_PORT}" \
      || "${STREAMLIT_PORT}" == "${VOICE_CHAT_PORT}" ]]; then
    echo "ERROR: FASTAPI_PORT, STREAMLIT_PORT, and VOICE_CHAT_PORT must be distinct." >&2
    exit 1
  fi
}

wait_for_port() {
  local port="$1"
  local label="$2"
  local timeout="${3:-120}"
  local elapsed=0

  echo "Waiting for ${label} on :${port} (timeout ${timeout}s)..."
  while (( elapsed < timeout )); do
    if port_listening "${port}"; then
      echo "  ${label} ready on :${port}"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "ERROR: ${label} did not become ready on :${port} within ${timeout}s" >&2
  return 1
}

wait_for_started_service() {
  local pid="$1"
  local port="$2"
  local label="$3"
  local timeout="${4:-30}"
  local elapsed=0

  echo "Waiting for ${label} on :${port} (timeout ${timeout}s)..."
  while (( elapsed < timeout )); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "ERROR: ${label} exited during startup." >&2
      wait "${pid}" 2>/dev/null || true
      return 1
    fi
    if port_listening "${port}"; then
      echo "  ${label} ready on :${port}"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "ERROR: ${label} did not become ready on :${port} within ${timeout}s" >&2
  return 1
}

kill_listeners_on_port() {
  local port="$1"
  local pids=""

  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true)
  fi

  if [[ -z "${pids}" ]] && command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  fi

  if [[ -z "${pids}" ]]; then
    echo "  :${port} — nothing listening"
    return 0
  fi

  for pid in ${pids}; do
    echo "  :${port} — stopping PID ${pid}"
    kill "${pid}" 2>/dev/null || true
  done
}

stop_stack() {
  echo "Stopping CityNerve services on known ports..."
  kill_listeners_on_port "${FASTAPI_PORT:-8000}"
  kill_listeners_on_port "${STREAMLIT_PORT:-8501}"
  kill_listeners_on_port "${VOICE_CHAT_PORT:-8503}"
  echo "Done."
}

cleanup() {
  local exit_code=$?
  echo ""
  echo "Shutting down CityNerve stack..."

  [[ -n "${PID_UVICORN}" ]] && kill "${PID_UVICORN}" 2>/dev/null || true
  [[ -n "${PID_STREAMLIT}" ]] && kill "${PID_STREAMLIT}" 2>/dev/null || true
  [[ -n "${PID_VOICE}" ]] && kill "${PID_VOICE}" 2>/dev/null || true

  if [[ "${STARTED_W1}" == 1 && -n "${PID_W1}" ]]; then
    kill "${PID_W1}" 2>/dev/null || true
  fi
  if [[ "${STARTED_W2}" == 1 && -n "${PID_W2}" ]]; then
    kill "${PID_W2}" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
  exit "${exit_code}"
}

start_ollama_server() {
  local port="$1"
  local label="$2"

  if port_listening "${port}"; then
    echo "Ollama already listening on :${port} (${label}) — skipping serve"
    return 0
  fi

  echo "Starting Ollama ${label} on :${port}"
  OLLAMA_HOST="127.0.0.1:${port}" "${OLLAMA_BIN}" serve &
  if [[ "${port}" == "11434" ]]; then
    PID_W2=$!
    STARTED_W2=1
  else
    PID_W1=$!
    STARTED_W1=1
  fi
  sleep 2
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_stack
  exit 0
fi

if ! command -v "${OLLAMA_BIN}" >/dev/null 2>&1; then
  echo "ERROR: '${OLLAMA_BIN}' not found in PATH." >&2
  echo "Install Ollama (https://ollama.com) or set OLLAMA_BIN to the binary path." >&2
  exit 1
fi

trap cleanup EXIT INT TERM

echo "==> Starting dual Ollama (W2 :11434, W1 :11436)"
start_ollama_server 11434 "W2 (analysis / Super)"
start_ollama_server 11436 "W1 (summary / Nano 12B)"

wait_for_port 11434 "Ollama W2"
wait_for_port 11436 "Ollama W1"

if [[ -x "${ROOT}/agent/scripts/check_endpoints.sh" ]]; then
  echo ""
  echo "==> Verifying Ollama endpoints (non-fatal)..."
  if ! "${ROOT}/agent/scripts/check_endpoints.sh"; then
    echo "WARN: endpoint check reported issues — stack will continue (models may be missing)." >&2
  fi
fi

require_distinct_ports
require_port_available "${FASTAPI_PORT}" "FASTAPI"
require_port_available "${STREAMLIT_PORT}" "STREAMLIT"
require_port_available "${VOICE_CHAT_PORT}" "VOICE_CHAT"

echo ""
echo "==> Starting FastAPI (uvicorn)"
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "${FASTAPI_PORT}" &
PID_UVICORN=$!

echo "==> Starting Streamlit"
"$PYTHON" -m streamlit run app.py --server.port "${STREAMLIT_PORT}" --server.address "${STREAMLIT_HOST}" &
PID_STREAMLIT=$!

echo "==> Starting Voice Reporting Line"
"$PYTHON" agent/harness/voice_bot.py --host "${VOICE_CHAT_HOST}" --port "${VOICE_CHAT_PORT}" &
PID_VOICE=$!

wait_for_started_service "${PID_UVICORN}" "${FASTAPI_PORT}" "FastAPI" 30
wait_for_started_service "${PID_STREAMLIT}" "${STREAMLIT_PORT}" "Streamlit" 30
wait_for_started_service "${PID_VOICE}" "${VOICE_CHAT_PORT}" "Voice Reporting Line" 30

cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║                    CityNerve Demo Stack Ready                    ║
╠══════════════════════════════════════════════════════════════════╣
║  Streamlit UI     http://${STREAMLIT_HOST}:${STREAMLIT_PORT}
║  FastAPI docs     http://127.0.0.1:${FASTAPI_PORT}/docs
║  Voice Reporting  http://${VOICE_CHAT_HOST}:${VOICE_CHAT_PORT}/client/
║  Ollama W2        http://127.0.0.1:11434/v1  (Super)             ║
║  Ollama W1        http://127.0.0.1:11436/v1  (Nano 12B)          ║
╠══════════════════════════════════════════════════════════════════╣
║  PIDs: uvicorn=${PID_UVICORN}  streamlit=${PID_STREAMLIT}  voice=${PID_VOICE}
EOF

if [[ "${STARTED_W2}" == 1 ]]; then
  echo "║         ollama-w2=${PID_W2} (started by this script)"
fi
if [[ "${STARTED_W1}" == 1 ]]; then
  echo "║         ollama-w1=${PID_W1} (started by this script)"
fi

cat <<EOF
╠══════════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop all services started by this script.       ║
╚══════════════════════════════════════════════════════════════════╝

EOF

wait "${PID_UVICORN}" "${PID_STREAMLIT}" "${PID_VOICE}"
