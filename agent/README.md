# Agent layer (harness + Workflow 1 + Workflow 2)

Shared Ollama client, dual-workflow profiles, and Nemotron gateways for FastAPI. GX10 dual-Ollama setup: [GX10-Nemotron-Ollama-Cheatsheet.md](../GX10-Nemotron-Ollama-Cheatsheet.md).

## Layout

```text
agent/
├── harness/              # settings, endpoints, client, health
├── evidence.py           # W1 evidence packet from pipe row + SHAP
├── gateway.py            # W1 orchestration
├── w2_gateway.py         # W2 multi-role + synthesis
├── prompts/              # workflow1_system.txt, w2/*.txt
├── schemas.py            # Pydantic contracts
├── scripts/              # check_endpoints.sh, ollama-dual-serve.example.sh
├── nemoclaw/             # sandboxes: hackathon-w1, nemotron-3-super
└── why_failing_agent.py  # legacy rule-based prose (unused; W1 replaces it in UI)
```

## Architecture

| Layer | Location | Role |
|-------|----------|------|
| Harness | `agent/harness/` | Dual Ollama profiles, async client, health |
| W1 | `gateway.py`, `evidence.py`, `w1_prompts.py` | Fast JSON pipe summary (Nano :11436) |
| W2 | `w2_gateway.py`, `w2_prompts.py`, `prompts/w2/` | Multi-role + synthesis (Super :11434) |

## Workflow profiles

| Profile | Ollama | Model | Output |
|---------|--------|-------|--------|
| `WorkflowProfile.WORKFLOW1` | `:11436` | `nemotron-nano:12b-v2` | JSON risk summary (128K context) |
| `WorkflowProfile.WORKFLOW2` | `:11434` | `nemotron-3-super:latest` | Multi-role reports + action plan |

Streamlit **never** calls Ollama — only FastAPI (`:8000`).

## Workflow 1

`GET /api/pipes/{pipe_id}/risk-summary` — Overview **Why Failing Agent** when pipes are selected in the queue (cached in session).

Modules: `schemas.py`, `evidence.py`, `llm_client.py`, `gateway.py`, `template_summary.py`.

## Workflow 2

`POST /api/analysis-runs` with `{"pipe_id": "...", "use_real": false}`

1. Build `AnalysisPacket` from pipe row
2. Four parallel Super calls (Engineer, Police, Field, Operations) — prompts in `prompts/w2/`
3. Synthesis → `final_summary.md` + `action_plan.json`
4. Artifacts under `data/analysis_runs/{run_id}/`

Risk Map: **Run multi-role analysis (Super)** (manual; does not auto-run).

Set `W2_PARALLEL=false` for sequential roles if GPU memory is tight.

## Config

Copy [`.env.example`](../.env.example) to repo root `.env` (WORKFLOW1/2, `W2_PARALLEL`).

Optional [`.env.example`](.env.example) in this folder adds NemoClaw sandbox names and port defaults.

## Health

- `GET /health` — both workflows
- `GET /health/workflow1` / `GET /health/workflow2`

Verify Ollama: `./agent/scripts/check_endpoints.sh`

## Quick start (GX10)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
./agent/scripts/check_endpoints.sh   # after dual Ollama is running
```

## Tests

```bash
.venv/bin/pytest agent/tests/ -v
```

Expect several minutes for a live W2 run (5 Super calls).

## NemoClaw

See [nemoclaw/README.md](nemoclaw/README.md) and [nemoclaw/investigate.md](nemoclaw/investigate.md).

## Legacy

- `why_failing_agent.py` — deprecated; UI uses Workflow 1 via `frontend/workflow1_ui.py`
