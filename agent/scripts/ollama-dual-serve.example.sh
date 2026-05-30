#!/usr/bin/env bash
# Example: run two Ollama servers on GX10 for dual-workflow hackathon setup.
# Copy/adapt paths for your install. See GX10-Nemotron-Ollama-Cheatsheet.md.
set -euo pipefail

OLLAMA_BIN="${OLLAMA_BIN:-ollama}"

echo "Starting Ollama W2 (analysis) on :11434 — model nemotron-3-super:latest"
OLLAMA_HOST=127.0.0.1:11434 "${OLLAMA_BIN}" serve &
PID_W2=$!

echo "Starting Ollama W1 (summary) on :11436 — model nemotron-nano:12b-v2"
OLLAMA_HOST=127.0.0.1:11436 "${OLLAMA_BIN}" serve &
PID_W1=$!

cleanup() {
  echo "Stopping Ollama servers..."
  kill "$PID_W1" "$PID_W2" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
echo "Preloading models (may take several minutes on first pull)..."
OLLAMA_HOST=127.0.0.1:11434 "${OLLAMA_BIN}" pull nemotron-3-super:latest
OLLAMA_HOST=127.0.0.1:11436 "${OLLAMA_BIN}" pull nemotron-nano:12b-v2

echo ""
echo "Dual Ollama ready:"
echo "  W2 analysis : http://127.0.0.1:11434/v1  (nemotron-3-super:latest)"
echo "  W1 summary  : http://127.0.0.1:11436/v1  (nemotron-nano:12b-v2)"
echo ""
echo "Verify: ./agent/scripts/check_endpoints.sh"
echo "Press Ctrl+C to stop both servers."

wait
