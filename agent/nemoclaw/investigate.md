# NemoClaw investigation guide

## Port map (GX10 localhost)

| Port | Service | Use |
|------|---------|-----|
| 11434 | Ollama W2 | `nemotron-3-super:latest` — analysis / multi-role |
| 11435 | (reserved) | NemoClaw dashboard / proxy if configured |
| 11436 | Ollama W1 | `nemotron-nano:12b-v2` — fast risk summaries |
| 8000 | FastAPI | `backend/main.py` — React UI calls this only |
| 5173 | React UI | `SubSurface-UI/` (Vite) |
| 8504 | Voice Reporting Line | `agent/harness/voice_bot.py` |

## List sandboxes

```bash
nemoclaw list
```

Expected for hackathon demo:

- `hackathon-w1` — W1 summary sandbox
- `nemotron-3-super` — W2 analysis sandbox

## Investigation workflow

1. Reproduce the issue in the relevant sandbox (`nemoclaw hackathon-w1 status`).
2. Check Ollama endpoints: `./agent/scripts/check_endpoints.sh`
3. Inspect harness health: `curl http://127.0.0.1:8000/health`
4. For W2 runs, check `data/analysis_runs/` artifacts.

## API boundary

Browser clients (React UI) should use FastAPI routes under `/api/*` — not Ollama URLs directly.
