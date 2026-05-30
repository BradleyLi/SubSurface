# Agent harness

Shared config and Ollama client for FastAPI LLM routes. Scaffolding for dual-workflow hackathon demo on GX10.

## Layout

```text
agent/
├── .env.example          # copy to repo root .env
├── harness/
│   ├── settings.py       # pydantic-settings from .env
│   ├── endpoints.py      # WorkflowProfile.WORKFLOW1 | WORKFLOW2
│   ├── client.py         # async chat() → Ollama /v1/chat/completions
│   └── health.py         # check_all(), check_profile()
├── scripts/
│   ├── check_endpoints.sh
│   └── ollama-dual-serve.example.sh
├── nemoclaw/             # fixed sandboxes: hackathon-w1, nemotron-3-super
└── why_failing_agent.py  # deterministic narrative (no LLM)
```

## Quick start

GX10 uses `python3` (not `python`) and PEP 668 — use a venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp agent/.env.example .env
./agent/scripts/check_endpoints.sh   # after Ollama is running
```

GX10 dual-Ollama setup: [GX10-Nemotron-Ollama-Cheatsheet.md](../GX10-Nemotron-Ollama-Cheatsheet.md)

## Workflow profiles

| Profile | Ollama | Model | Context window | Output | Default `max_tokens` |
|---------|--------|-------|----------------|--------|----------------------|
| `WorkflowProfile.WORKFLOW1` | `:11436` | `nemotron-nano:12b-v2` | **128K** (incl. VL variant) | 2–3 sentence risk summary | 256 |
| `WorkflowProfile.WORKFLOW2` | `:11434` | `nemotron-3-super:latest` | model default | Multi-page analysis report | 1,000,000 |

W1 JSON table inputs + the summary reply must fit within the 128K context window. With typical pipe/SHAP tables this is ample headroom.

## FastAPI integration

Streamlit **never** calls Ollama. It uses `backend/` (port 8000). FastAPI selects JSON tables and calls Workflow 1:

```python
from agent.harness import (
    TABLE_PIPE_PROFILE,
    TABLE_SHAP,
    summarize,
)

# Build tables from pipe row, SHAP dict, etc.
summary = await summarize(
    {
        TABLE_PIPE_PROFILE: [pipe_record],       # one row from /api/pipes
        TABLE_SHAP: shap_rows,                    # optional feature contributions
        "network_context": [network_stats_row],  # any extra selected tables
    }
)
```

Suggested table keys: `pipe_profile`, `risk_drivers`, `shap_drivers`, `network_context`, `cascade_impact`. Pass only the tables relevant to the summary.

Low-level transport (Workflow 2 or custom prompts):

```python
from agent.harness.client import chat
from agent.harness.endpoints import WorkflowProfile

report = await chat(
    WorkflowProfile.WORKFLOW2,
    messages=[{"role": "user", "content": "Produce a full multi-section analysis report."}],
)
```

Future routes (not implemented yet): `/pipes/{id}/risk-summary`, `/analysis-runs`.

## Ports

| Service | Default port |
|---------|--------------|
| FastAPI | 8000 |
| Streamlit | 8501 |
| Ollama W2 | 11434 |
| Ollama W1 | 11436 |

## NemoClaw

See [nemoclaw/README.md](nemoclaw/README.md) and [nemoclaw/investigate.md](nemoclaw/investigate.md).

## Existing modules

- `why_failing_agent.py` — rule-based failure explanations (used today without LLM)
