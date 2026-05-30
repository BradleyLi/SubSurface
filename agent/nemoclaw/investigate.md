# NemoClaw investigation guide

## Port map (GX10 localhost)

| Port | Service | Use |
|------|---------|-----|
| 11434 | Ollama W2 | `nemotron-3-super:latest` — analysis / multi-role |
| 11435 | (reserved) | NemoClaw dashboard / proxy if configured |
| 11436 | Ollama W1 | `nemotron-nano:12b-v2` — fast risk summaries |
| 8000 | FastAPI | `backend/main.py` — Streamlit calls this only |
| 8501 | Streamlit | `app.py` multipage UI |

## List sandboxes

```bash
nemoclaw list
```

Expected for hackathon demo:

- `hackathon-w1` → Ollama `http://127.0.0.1:11436/v1`
- `nemotron-3-super` → Ollama `http://127.0.0.1:11434/v1`

## Direct Ollama vs sandbox

| Path | Caller | When |
|------|--------|------|
| `agent.harness.client.chat(WorkflowProfile.WORKFLOW1, ...)` | FastAPI | Deterministic W1 summary routes, low latency |
| `agent.harness.client.chat(WorkflowProfile.WORKFLOW2, ...)` | FastAPI | W2 orchestration (future parallel calls) |
| `nemoclaw connect hackathon-w1` | Human / agent | Interactive investigation, tool use |
| `nemoclaw connect nemotron-3-super` | Human / agent | Deep analysis sessions |

Streamlit pages under `pages/` and `app.py` should use `api_client.py` / `CITYNERVE_API_URL` — not Ollama URLs.

## Quick checks

```bash
./agent/scripts/check_endpoints.sh
curl -s http://127.0.0.1:11436/v1/models | head
curl -s http://127.0.0.1:11434/v1/models | head
```
