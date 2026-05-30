# NemoClaw — single-operator hackathon setup

Fixed sandbox names for one GX10 operator (no per-developer naming).

| Workflow | Sandbox | Ollama port | Model |
|----------|---------|-------------|-------|
| W1 (summary) | `hackathon-w1` | 11436 | `nemotron-nano:12b-v2` |
| W2 (analysis) | `nemotron-3-super` | 11434 | `nemotron-3-super:latest` |

## One-time setup

1. Start dual Ollama (see [GX10-Nemotron-Ollama-Cheatsheet.md](../../GX10-Nemotron-Ollama-Cheatsheet.md) or `agent/scripts/ollama-dual-serve.example.sh`).
2. Onboard W1 sandbox:

   ```bash
   ./agent/nemoclaw/onboard-hackathon-w1.sh
   ```

   When prompted, point the sandbox at `http://127.0.0.1:11436/v1`.

3. W2 reuses the existing `nemotron-3-super` sandbox (11434). If missing:

   ```bash
   NEMOCLAW_MODEL=nemotron-3-super:latest nemoclaw onboard --name nemotron-3-super
   ```

## Health

```bash
nemoclaw list
nemoclaw hackathon-w1 status
nemoclaw nemotron-3-super status
```

Recover if unhealthy:

```bash
nemoclaw hackathon-w1 recover
nemoclaw nemotron-3-super recover
```

## When to use NemoClaw vs direct Ollama

- **FastAPI / `agent.harness.client`** — low-latency programmatic calls (W1 risk summaries, future W2 routes). Streamlit never calls Ollama directly.
- **NemoClaw** — multi-step agent investigation, dashboard, `nemoclaw connect` sessions. See [investigate.md](investigate.md).
