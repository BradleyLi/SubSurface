#!/usr/bin/env bash
# CityNerve full demo stack: dual Ollama, FastAPI, React UI (Vite), Voice Reporting Line.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export CITYNERVE_LOG_LEVEL="${CITYNERVE_LOG_LEVEL:-INFO}"

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
OLLAMA_W2_PORT="${OLLAMA_W2_PORT:-11434}"
OLLAMA_W1_PORT="${OLLAMA_W1_PORT:-11436}"
# When W1 uses a non-default port (e.g. Cursor forwards :11436), sync workflow URL.
if [[ "${OLLAMA_W1_PORT}" != "11436" ]]; then
  export WORKFLOW1_OPENAI_BASE_URL="http://127.0.0.1:${OLLAMA_W1_PORT}/v1"
fi
UI_HOST="${UI_HOST:-0.0.0.0}"
VOICE_CHAT_HOST="${VOICE_CHAT_HOST:-0.0.0.0}"
UI_DIR="${ROOT}/SubSurface-UI"

# Static app ports. Edit these defaults, or override per run:
#   FASTAPI_PORT=8000 UI_PORT=5173 VOICE_CHAT_PORT=8504 ./scripts/run_citynerve.sh
# Default voice :8504 avoids :8503 (often taken by Cursor IDE port forwarding).
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
VOICE_CHAT_PORT="${VOICE_CHAT_PORT:-8504}"
export FASTAPI_PORT UI_PORT VOICE_CHAT_PORT
export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${FASTAPI_PORT}}"

port_in_use() {
  local port="$1"
  "$PYTHON" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
PID_UI=""
PID_VOICE=""

port_listening() {
  local port="$1"
  port_in_use "$port"
}

describe_port_listeners() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep -E ":${port}([[:space:]]|$)" || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
  fi
}

require_port_available() {
  local port="$1"
  local label="$2"

  if port_listening "${port}"; then
    echo "ERROR: configured ${label} port :${port} is already in use." >&2
    describe_port_listeners "${port}" >&2
    echo "Set ${label}_PORT to a free port, or run '$0 --stop' to stop CityNerve services." >&2
    exit 1
  fi
}

resolve_voice_chat_port() {
  local base="${VOICE_CHAT_PORT}"
  local port="${base}"
  local max="${VOICE_CHAT_PORT_ATTEMPTS:-20}"
  local try=0

  while (( try <= max )); do
    if ! port_listening "${port}"; then
      if [[ "${port}" != "${base}" ]]; then
        echo "Using Voice Reporting Line on :${port} (:${base} was busy)."
      fi
      VOICE_CHAT_PORT="${port}"
      export VOICE_CHAT_PORT
      return 0
    fi

    if (( try == 0 )); then
      echo "WARN: Voice port :${port} is busy:" >&2
      describe_port_listeners "${port}" >&2
      kill_listeners_on_port "${port}"
      if ! port_listening "${port}"; then
        return 0
      fi
      echo "WARN: Could not free :${port} (Cursor IDE often forwards :8503) — trying next port." >&2
    fi

    port=$((port + 1))
    try=$((try + 1))
  done

  echo "ERROR: No free voice port from :${base} through :$((base + max))." >&2
  exit 1
}

require_distinct_ports() {
  if [[ "${FASTAPI_PORT}" == "${UI_PORT}" \
      || "${FASTAPI_PORT}" == "${VOICE_CHAT_PORT}" \
      || "${UI_PORT}" == "${VOICE_CHAT_PORT}" ]]; then
    echo "ERROR: FASTAPI_PORT, UI_PORT, and VOICE_CHAT_PORT must be distinct." >&2
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

start_voice_service() {
  local base="${VOICE_CHAT_PORT}"
  local max="${VOICE_CHAT_PORT_ATTEMPTS:-20}"
  local try=0
  local port

  while (( try <= max )); do
    port=$((base + try))

    if [[ "${port}" == "${FASTAPI_PORT}" || "${port}" == "${UI_PORT}" ]]; then
      try=$((try + 1))
      continue
    fi

    if port_listening "${port}"; then
      echo "WARN: Voice port :${port} became busy before startup:" >&2
      describe_port_listeners "${port}" >&2
      try=$((try + 1))
      continue
    fi

    VOICE_CHAT_PORT="${port}"
    export VOICE_CHAT_PORT

    if [[ "${port}" != "${base}" ]]; then
      echo "Using Voice Reporting Line on :${port} (:${base} was not available)."
    fi

    echo "==> Starting Voice Reporting Line"
    "$PYTHON" agent/harness/voice_bot.py --host "${VOICE_CHAT_HOST}" --port "${VOICE_CHAT_PORT}" &
    PID_VOICE=$!

    if wait_for_started_service "${PID_VOICE}" "${VOICE_CHAT_PORT}" "Voice Reporting Line" 30; then
      return 0
    fi

    PID_VOICE=""
    echo "WARN: Voice Reporting Line failed on :${VOICE_CHAT_PORT}; trying next port." >&2
    try=$((try + 1))
  done

  echo "ERROR: No working voice port from :${base} through :$((base + max))." >&2
  return 1
}

pid_command_name() {
  local pid="$1"
  if [[ -r "/proc/${pid}/comm" ]]; then
    tr -d '\n' < "/proc/${pid}/comm"
    return 0
  fi
  if command -v ps >/dev/null 2>&1; then
    ps -p "${pid}" -o comm= 2>/dev/null | tr -d ' '
  fi
}

pid_owner() {
  local pid="$1"
  if [[ -e "/proc/${pid}" ]]; then
    stat -c '%U' "/proc/${pid}" 2>/dev/null && return 0
  fi
  if command -v ps >/dev/null 2>&1; then
    ps -o user= -p "${pid}" 2>/dev/null | tr -d ' '
  fi
}

pids_on_port() {
  local port="$1"
  local pids=""
  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -tlnp 2>/dev/null | grep -E ":${port}([[:space:]]|$)" | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true)
  fi
  if [[ -z "${pids}" ]] && command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  fi
  echo "${pids}"
}

port_held_by_cursor() {
  local port="$1"
  local pid comm
  for pid in $(pids_on_port "${port}"); do
    comm="$(pid_command_name "${pid}")"
    if [[ "${comm}" == "cursor" ]]; then
      return 0
    fi
  done
  return 1
}

non_cursor_pids_on_port() {
  local port="$1"
  local pid comm
  for pid in $(pids_on_port "${port}"); do
    comm="$(pid_command_name "${pid}")"
    if [[ "${comm}" != "cursor" ]]; then
      echo "${pid}"
    fi
  done
}

port_only_held_by_cursor() {
  local port="$1"
  if ! port_held_by_cursor "${port}"; then
    return 1
  fi

  [[ -z "$(non_cursor_pids_on_port "${port}")" ]]
}

cursor_port_forward_hint() {
  local port="$1"
  local role="${2:-service}"
  echo "ERROR: Port :${port} (${role}) is held by Cursor IDE port forwarding, not your ${role}." >&2
  echo "  In Cursor: Ports panel → stop/remove the forward for :${port}, then retry." >&2
  echo "  Or use alternate ports, e.g.:" >&2
  echo "    FASTAPI_PORT=9001 UI_PORT=5174 VOICE_CHAT_PORT=8505 OLLAMA_W1_PORT=11437 ./scripts/run_citynerve.sh" >&2
}

kill_listeners_on_port() {
  local port="$1"
  local pids=""
  local killed_any=0

  pids="$(pids_on_port "${port}")"

  if [[ -z "${pids}" ]]; then
    if port_listening "${port}"; then
      if port_held_by_cursor "${port}"; then
        echo "  :${port} — in use by Cursor IDE port forward (cannot stop from script)"
      else
        echo "  :${port} — in use (could not resolve PID; try: ss -tlnp | grep :${port})"
      fi
    else
      echo "  :${port} — nothing listening"
    fi
    return 0
  fi

  for pid in ${pids}; do
    local comm
    comm="$(pid_command_name "${pid}")"
    if [[ "${comm}" == "cursor" ]]; then
      echo "  :${port} — skipped Cursor IDE (PID ${pid}); use another VOICE_CHAT_PORT"
      continue
    fi
    echo "  :${port} — stopping ${comm:-process} (PID ${pid})"
    kill "${pid}" 2>/dev/null || true
    killed_any=1
  done

  if [[ "${killed_any}" == 1 ]]; then
    if ! wait_for_non_cursor_listeners_to_clear "${port}" 10; then
      echo "  :${port} — still in use after waiting; forcing shutdown"
      for pid in ${pids}; do
        local comm
        comm="$(pid_command_name "${pid}")"
        if [[ "${comm}" != "cursor" ]] && kill -0 "${pid}" 2>/dev/null; then
          kill -KILL "${pid}" 2>/dev/null || true
        fi
      done

      wait_for_non_cursor_listeners_to_clear "${port}" 5 || {
        echo "  :${port} — still in use after forced shutdown; checking ownership"
        escalate_foreign_listeners_on_port "${port}"
        if [[ -n "$(non_cursor_pids_on_port "${port}")" ]]; then
          echo "  :${port} — still in use"
          describe_port_listeners "${port}"
        fi
      }
    fi
  fi
}

wait_for_port_to_clear() {
  local port="$1"
  local timeout="${2:-10}"
  local attempts=$((timeout * 5))
  local attempt=0

  while (( attempt < attempts )); do
    if ! port_listening "${port}"; then
      return 0
    fi
    sleep 0.2
    attempt=$((attempt + 1))
  done

  return 1
}

wait_for_non_cursor_listeners_to_clear() {
  local port="$1"
  local timeout="${2:-10}"
  local attempts=$((timeout * 5))
  local attempt=0

  while (( attempt < attempts )); do
    if [[ -z "$(non_cursor_pids_on_port "${port}")" ]]; then
      return 0
    fi
    sleep 0.2
    attempt=$((attempt + 1))
  done

  return 1
}

# Handle leftover listeners owned by another user (e.g. a root-owned uvicorn
# from a previous `sudo` run). A normal `kill` from this user silently fails on
# those, so escalate with sudo when possible, otherwise print the exact command.
escalate_foreign_listeners_on_port() {
  local port="$1"
  local me pid owner comm escalated=0 hint_printed=0
  me="$(id -un 2>/dev/null || echo "${USER:-}")"

  for pid in $(non_cursor_pids_on_port "${port}"); do
    kill -0 "${pid}" 2>/dev/null || continue
    owner="$(pid_owner "${pid}")"
    comm="$(pid_command_name "${pid}")"

    # Only escalate for processes we don't own; same-user survivors are a
    # different problem and were already kill -KILL'd above.
    if [[ -z "${owner}" || "${owner}" == "${me}" ]]; then
      continue
    fi

    echo "  :${port} — leftover ${comm:-process} (PID ${pid}) is owned by '${owner}', not '${me}'" >&2

    if command -v sudo >/dev/null 2>&1; then
      if sudo -n true 2>/dev/null; then
        echo "  :${port} — escalating with passwordless sudo to stop PID ${pid}" >&2
        sudo -n kill -KILL "${pid}" 2>/dev/null || true
        escalated=1
      elif [[ -t 0 ]]; then
        echo "  :${port} — requesting sudo to stop PID ${pid} (you may be prompted for your password)" >&2
        sudo kill -KILL "${pid}" 2>/dev/null || true
        escalated=1
      else
        if (( hint_printed == 0 )); then
          echo "  :${port} — cannot stop '${owner}'-owned leftover without privileges. Run, then retry:" >&2
          hint_printed=1
        fi
        echo "      sudo kill -9 ${pid}" >&2
      fi
    else
      if (( hint_printed == 0 )); then
        echo "  :${port} — cannot stop '${owner}'-owned leftover (no sudo found). As '${owner}' run, then retry:" >&2
        hint_printed=1
      fi
      echo "      kill -9 ${pid}" >&2
    fi
  done

  if (( escalated == 1 )); then
    wait_for_non_cursor_listeners_to_clear "${port}" 5 || true
  fi
}

stop_stack() {
  echo "Stopping CityNerve services on known ports..."
  kill_listeners_on_port "${FASTAPI_PORT:-8000}"
  kill_listeners_on_port "${UI_PORT:-5173}"
  kill_listeners_on_port "${VOICE_CHAT_PORT:-8504}"
  echo "Done."
}

cleanup() {
  local exit_code=$?
  echo ""
  echo "Shutting down CityNerve stack..."

  [[ -n "${PID_UVICORN}" ]] && kill "${PID_UVICORN}" 2>/dev/null || true
  [[ -n "${PID_UI}" ]] && kill "${PID_UI}" 2>/dev/null || true
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

ollama_endpoint_healthy() {
  local port="$1"
  local max_time="${2:-8}"

  command -v curl >/dev/null 2>&1 || return 1
  curl -sfS \
    --connect-timeout 2 \
    --max-time "${max_time}" \
    "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
}

start_ollama_server() {
  local port="$1"
  local label="$2"

  if port_listening "${port}"; then
    if ollama_endpoint_healthy "${port}"; then
      echo "Ollama already listening on :${port} (${label}) — skipping serve"
      return 0
    fi

    if port_only_held_by_cursor "${port}"; then
      cursor_port_forward_hint "${port}" "Ollama ${label}"
      return 1
    fi

    echo "WARN: Ollama on :${port} (${label}) is listening but unresponsive — restarting"
    kill_listeners_on_port "${port}"
    if port_listening "${port}"; then
      if port_only_held_by_cursor "${port}"; then
        cursor_port_forward_hint "${port}" "Ollama ${label}"
      else
        echo "ERROR: Could not free unresponsive Ollama port :${port}" >&2
      fi
      return 1
    fi
  fi

  echo "Starting Ollama ${label} on :${port}"
  export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-24h}"
  export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"
  # Serve the 4 Workflow-2 analysis roles (engineer/police/field/operations)
  # concurrently from one loaded model instead of queuing them one slot at a
  # time. Ollama splits the model's KV cache into this many slots (shared
  # weights, per-slot KV). The GB10's unified memory (~111 GiB) easily fits the
  # model weights plus 4 KV slots. Override per run, e.g. OLLAMA_NUM_PARALLEL=2.
  export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"
  OLLAMA_HOST="127.0.0.1:${port}" "${OLLAMA_BIN}" serve &
  if [[ "${port}" == "${OLLAMA_W2_PORT}" ]]; then
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

# Reclaim configured stack ports (and legacy :8503 voice default if still set in env).
echo "==> Ensuring stack ports are free (${FASTAPI_PORT}, ${UI_PORT}, ${VOICE_CHAT_PORT})…"
kill_listeners_on_port "${FASTAPI_PORT}"
kill_listeners_on_port "${UI_PORT}"
kill_listeners_on_port "${VOICE_CHAT_PORT}"
if [[ "${VOICE_CHAT_PORT}" != "8503" ]]; then
  kill_listeners_on_port 8503
fi

if ! command -v "${OLLAMA_BIN}" >/dev/null 2>&1; then
  echo "ERROR: '${OLLAMA_BIN}' not found in PATH." >&2
  echo "Install Ollama (https://ollama.com) or set OLLAMA_BIN to the binary path." >&2
  exit 1
fi

trap cleanup EXIT INT TERM

echo "==> Starting dual Ollama (W2 :${OLLAMA_W2_PORT}, W1 :${OLLAMA_W1_PORT})"
start_ollama_server "${OLLAMA_W2_PORT}" "W2 (analysis / Super)"
start_ollama_server "${OLLAMA_W1_PORT}" "W1 (summary / Nano 12B)"

wait_for_port "${OLLAMA_W2_PORT}" "Ollama W2"
wait_for_port "${OLLAMA_W1_PORT}" "Ollama W1"

if [[ -x "${ROOT}/agent/scripts/check_endpoints.sh" ]]; then
  echo ""
  echo "==> Verifying Ollama endpoints (non-fatal)..."
  if ! "${ROOT}/agent/scripts/check_endpoints.sh"; then
    echo "WARN: endpoint check reported issues — stack will continue (models may be missing)." >&2
  fi
fi

require_distinct_ports
if port_listening "${FASTAPI_PORT}" && port_only_held_by_cursor "${FASTAPI_PORT}"; then
  cursor_port_forward_hint "${FASTAPI_PORT}" "FastAPI"
  exit 1
fi
if port_listening "${UI_PORT}" && port_only_held_by_cursor "${UI_PORT}"; then
  cursor_port_forward_hint "${UI_PORT}" "React UI (Vite)"
  exit 1
fi
require_port_available "${FASTAPI_PORT}" "FASTAPI"
require_port_available "${UI_PORT}" "UI"
resolve_voice_chat_port
require_distinct_ports
export VITE_VOICE_CHAT_PORT="${VOICE_CHAT_PORT}"

if [[ ! -d "${UI_DIR}" ]]; then
  echo "ERROR: React UI not found at ${UI_DIR}" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: 'npm' not found in PATH (required for SubSurface-UI)." >&2
  echo "Install Node.js (https://nodejs.org) or run the API only: uvicorn backend.main:app --port ${FASTAPI_PORT}" >&2
  exit 1
fi

if [[ ! -d "${UI_DIR}/node_modules" ]]; then
  echo "==> Installing SubSurface-UI dependencies (npm install)..."
  (cd "${UI_DIR}" && npm install)
fi

if [[ ! -f "${UI_DIR}/.env" ]]; then
  echo "WARN: ${UI_DIR}/.env missing — copy .env.example and set VITE_MAPBOX_TOKEN for the map." >&2
fi

echo ""
echo "==> Starting FastAPI (uvicorn)"
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "${FASTAPI_PORT}" &
PID_UVICORN=$!

wait_for_started_service "${PID_UVICORN}" "${FASTAPI_PORT}" "FastAPI" 30
start_voice_service
export VITE_VOICE_CHAT_PORT="${VOICE_CHAT_PORT}"

echo "==> Starting React UI (Vite → API ${VITE_API_PROXY_TARGET}, voice :${VOICE_CHAT_PORT})"
(cd "${UI_DIR}" && npm run dev -- --host "${UI_HOST}" --port "${UI_PORT}") &
PID_UI=$!

wait_for_started_service "${PID_UI}" "${UI_PORT}" "React UI (Vite)" 60

cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║                    CityNerve Demo Stack Ready                    ║
╠══════════════════════════════════════════════════════════════════╣
║  React UI (Vite)  http://${UI_HOST}:${UI_PORT}
║  FastAPI docs     http://127.0.0.1:${FASTAPI_PORT}/docs
║  Voice Reporting  http://${VOICE_CHAT_HOST}:${VOICE_CHAT_PORT}/client/
║  Ollama W2        http://127.0.0.1:${OLLAMA_W2_PORT}/v1  (Super)             ║
║  Ollama W1        http://127.0.0.1:${OLLAMA_W1_PORT}/v1  (Nano 12B)          ║
╠══════════════════════════════════════════════════════════════════╣
║  PIDs: uvicorn=${PID_UVICORN}  vite=${PID_UI}  voice=${PID_VOICE}
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

wait "${PID_UVICORN}" "${PID_UI}" "${PID_VOICE}"
