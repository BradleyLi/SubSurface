# GX10 — Nemotron + Ollama cheatsheet

Single-operator hackathon setup on NVIDIA GX10: dual local Ollama instances and NemoClaw sandboxes.

Full harness docs: [agent/README.md](agent/README.md).

## Dual Ollama

| Profile | Port | Model | Context window | Env var |
|---------|------|-------|----------------|---------|
| Workflow 1 (summary) | **11436** | `nemotron-nano:12b-v2` | **128K** tokens | `WORKFLOW1_OPENAI_BASE_URL` |
| Workflow 2 (analysis) | **11434** | `nemotron-3-super:latest` | (model default) | `WORKFLOW2_OPENAI_BASE_URL` |

**W1 model note:** Nemotron-Nano 12B v2 (including its Vision-Language variant) supports up to **128K tokens** of combined prompt + completion. W1 summaries only use ~256 output tokens; the large window is headroom for selected JSON table inputs.

### Start both servers

```bash
chmod +x agent/scripts/ollama-dual-serve.example.sh
./agent/scripts/ollama-dual-serve.example.sh
```

Or manually in two terminals:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
OLLAMA_HOST=127.0.0.1:11436 ollama serve
```

Preload models:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama pull nemotron-3-super:latest
OLLAMA_HOST=127.0.0.1:11436 ollama pull nemotron-nano:12b-v2
```

### Verify

```bash
./agent/scripts/check_endpoints.sh
curl -s http://127.0.0.1:11436/v1/models
curl -s http://127.0.0.1:11434/v1/models
```

## NemoClaw sandboxes

| Sandbox | Ollama endpoint |
|---------|-----------------|
| `hackathon-w1` | `http://127.0.0.1:11436/v1` |
| `nemotron-3-super` | `http://127.0.0.1:11434/v1` |

One-time W1 onboard: `./agent/nemoclaw/onboard-hackathon-w1.sh`

Details: [agent/nemoclaw/README.md](agent/nemoclaw/README.md)

## App stack start order

1. Ollama W2 + W1 (11434, 11436)
2. `nemoclaw hackathon-w1 status` and `nemoclaw nemotron-3-super status`
3. FastAPI: `uvicorn backend.main:app --host 127.0.0.1 --port 8000`
4. Streamlit: `streamlit run app.py --server.port 8501`

Copy env: `cp agent/.env.example .env`

## FastAPI harness import

When adding LLM routes to `backend/main.py`:

```python
from agent.harness.client import chat
from agent.harness.endpoints import WorkflowProfile

# summary_text = await chat(WorkflowProfile.WORKFLOW1, messages=[...], max_tokens=256)
```

Streamlit calls FastAPI only (`CITYNERVE_API_URL` / port 8000), never Ollama directly.
