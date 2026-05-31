#!/usr/bin/env bash
# Verify dual Ollama endpoints (W1 @ 11436, W2 @ 11434) and optional NemoClaw sandboxes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT}/.env"

declare -A ENV_OVERRIDES=()
for name in \
  WORKFLOW1_OPENAI_BASE_URL \
  WORKFLOW2_OPENAI_BASE_URL \
  WORKFLOW1_MODEL \
  WORKFLOW2_MODEL \
  NEMOCLAW_W1_SANDBOX \
  NEMOCLAW_W2_SANDBOX \
  OPENAI_API_KEY \
  ENDPOINT_CHECK_CONNECT_TIMEOUT \
  ENDPOINT_CHECK_MAX_TIME; do
  if [[ -v "${name}" ]]; then
    ENV_OVERRIDES["${name}"]="${!name}"
  fi
done

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
elif [[ -f "${ROOT}/agent/.env.example" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ROOT}/agent/.env.example" && set +a
fi

for name in "${!ENV_OVERRIDES[@]}"; do
  export "${name}=${ENV_OVERRIDES[${name}]}"
done

W1_URL="${WORKFLOW1_OPENAI_BASE_URL:-http://127.0.0.1:11436/v1}"
W2_URL="${WORKFLOW2_OPENAI_BASE_URL:-http://127.0.0.1:11434/v1}"
W1_MODEL="${WORKFLOW1_MODEL:-nemotron-nano:12b-v2}"
W2_MODEL="${WORKFLOW2_MODEL:-nemotron-3-super:latest}"
NC_W1="${NEMOCLAW_W1_SANDBOX:-hackathon-w1}"
NC_W2="${NEMOCLAW_W2_SANDBOX:-nemotron-3-super}"
API_KEY="${OPENAI_API_KEY:-ollama}"
CURL_CONNECT_TIMEOUT="${ENDPOINT_CHECK_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${ENDPOINT_CHECK_MAX_TIME:-20}"

failures=0

check_ollama() {
  local label="$1"
  local base_url="$2"
  local expected_model="$3"
  local models_url="${base_url%/}/models"

  echo "==> Checking ${label} at ${base_url}"
  if ! response="$(
    curl -sfS \
      --connect-timeout "${CURL_CONNECT_TIMEOUT}" \
      --max-time "${CURL_MAX_TIME}" \
      -H "Authorization: Bearer ${API_KEY}" \
      "${models_url}" 2>&1
  )"; then
    echo "FAIL: ${label} unreachable (${models_url})"
    echo "      ${response}"
    failures=$((failures + 1))
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
ids = [m.get('id','') for m in data.get('data', [])]
expected = '${expected_model}'
ok = expected in ids or any(expected.split(':')[0] in m for m in ids)
print('Models:', ', '.join(ids) if ids else '(none)')
sys.exit(0 if ok else 1)
" <<< "$response"; then
      echo "FAIL: ${label} model ${expected_model} not found"
      failures=$((failures + 1))
      return
    fi
  else
    echo "Models response OK (install python3 for model name validation)"
  fi
  echo "OK: ${label}"
}

check_nemoclaw() {
  local sandbox="$1"
  echo "==> Checking NemoClaw sandbox: ${sandbox}"
  if ! command -v nemoclaw >/dev/null 2>&1; then
    echo "SKIP: nemoclaw CLI not installed"
    return
  fi
  if nemoclaw "${sandbox}" status >/dev/null 2>&1; then
    echo "OK: ${sandbox}"
  else
    echo "WARN: ${sandbox} not healthy (run onboard or recover — see agent/nemoclaw/README.md)"
    failures=$((failures + 1))
  fi
}

check_ollama "Workflow 1 (summary)" "$W1_URL" "$W1_MODEL"
check_ollama "Workflow 2 (analysis)" "$W2_URL" "$W2_MODEL"

if command -v nemoclaw >/dev/null 2>&1; then
  echo ""
  echo "==> NemoClaw sandboxes"
  nemoclaw list 2>/dev/null || true
  check_nemoclaw "$NC_W1"
  check_nemoclaw "$NC_W2"
else
  echo ""
  echo "SKIP: nemoclaw not in PATH (Ollama checks only)"
fi

echo ""
if [[ "$failures" -gt 0 ]]; then
  echo "FAILED: ${failures} check(s). See agent/README.md and GX10-Nemotron-Ollama-Cheatsheet.md"
  exit 1
fi
echo "All endpoint checks passed."
