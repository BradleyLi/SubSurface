#!/usr/bin/env bash
# GX10 dual Ollama: W2 :11434 (Super), W1 :11436 (Nano 12B v2).
# See GX10-Nemotron-Ollama-Cheatsheet.md and Nemotron_Inference_Cheatsheet.txt
set -euo pipefail

OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
OLLAMA_MODELS="${OLLAMA_MODELS:-/home/asus/.ollama/models}"
export OLLAMA_MODELS

PID_W1=""
PID_W2=""
STARTED_W1=0
STARTED_W2=0

port_listening() {
  local port="$1"
  ss -tln 2>/dev/null | grep -q ":${port} " || \
    curl -sf "http://127.0.0.1:${port}/api/version" >/dev/null 2>&1
}

start_server() {
  local port="$1"
  local label="$2"
  if port_listening "${port}"; then
    echo "Ollama already listening on :${port} (${label}) — skipping serve"
    return 0
  fi
  echo "Starting Ollama ${label} on :${port}"
  # Serve the 4 Workflow-2 analysis roles concurrently (shared weights,
  # per-slot KV cache) instead of queuing them. Override per run if needed.
  export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"
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

ensure_w1_model() {
  local host="127.0.0.1:11436"
  if OLLAMA_HOST="${host}" "${OLLAMA_BIN}" list 2>/dev/null | grep -q 'nemotron-nano:12b-v2'; then
    echo "W1 model nemotron-nano:12b-v2 already present on :11436"
    return 0
  fi
  echo "W1 tag nemotron-nano:12b-v2 is not in the registry — creating from GGUF on :11436"
  echo "  (see Nemotron_Inference_Cheatsheet.txt)"
  OLLAMA_HOST="${host}" "${OLLAMA_BIN}" pull \
    hf.co/bartowski/nvidia_NVIDIA-Nemotron-Nano-12B-v2-GGUF:Q4_K_M
  local modelfile="${HOME}/Modelfile.nemotron-12b-v2"
  if [[ ! -f "${modelfile}" ]]; then
    cat > "${modelfile}" << 'EOF'
FROM hf.co/bartowski/nvidia_NVIDIA-Nemotron-Nano-12B-v2-GGUF:Q4_K_M
EOF
  fi
  OLLAMA_HOST="${host}" "${OLLAMA_BIN}" create nemotron-nano:12b-v2 -f "${modelfile}"
}

cleanup() {
  if [[ "${STARTED_W1}" == 1 || "${STARTED_W2}" == 1 ]]; then
    echo "Stopping Ollama servers started by this script..."
    [[ -n "${PID_W1}" ]] && kill "${PID_W1}" 2>/dev/null || true
    [[ -n "${PID_W2}" ]] && kill "${PID_W2}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

start_server 11434 "W2 (analysis / Super)"
start_server 11436 "W1 (summary / Nano 12B)"

echo "Ensuring models..."
OLLAMA_HOST=127.0.0.1:11434 "${OLLAMA_BIN}" pull nemotron-3-super:latest
ensure_w1_model

echo ""
echo "Dual Ollama ready:"
echo "  W2 : http://127.0.0.1:11434/v1  (nemotron-3-super:latest)"
echo "  W1 : http://127.0.0.1:11436/v1  (nemotron-nano:12b-v2)"
echo ""
echo "Verify: ./agent/scripts/check_endpoints.sh"

if [[ "${STARTED_W1}" == 1 || "${STARTED_W2}" == 1 ]]; then
  echo "Press Ctrl+C to stop servers started by this script."
  wait
else
  trap - EXIT INT TERM
  echo "Servers were already running — script exiting (nothing to wait on)."
fi
