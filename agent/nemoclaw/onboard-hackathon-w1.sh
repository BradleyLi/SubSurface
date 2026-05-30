#!/usr/bin/env bash
# One-time onboard for Workflow 1 NemoClaw sandbox on GX10.
set -euo pipefail

SANDBOX="${NEMOCLAW_W1_SANDBOX:-hackathon-w1}"
MODEL="${NEMOCLAW_MODEL:-nemotron-nano:12b-v2}"
OLLAMA_URL="${WORKFLOW1_OPENAI_BASE_URL:-http://127.0.0.1:11436/v1}"

echo "Onboarding NemoClaw sandbox: ${SANDBOX}"
echo "  Model:    ${MODEL}"
echo "  Endpoint: ${OLLAMA_URL}"
echo ""
echo "When the wizard prompts for the OpenAI-compatible endpoint, use:"
echo "  ${OLLAMA_URL}"
echo ""

if ! command -v nemoclaw >/dev/null 2>&1; then
  echo "ERROR: nemoclaw CLI not found. Install NemoClaw first."
  exit 1
fi

NEMOCLAW_MODEL="${MODEL}" nemoclaw onboard --name "${SANDBOX}"

echo ""
echo "Verify: nemoclaw ${SANDBOX} status"
echo "        nemoclaw list"
