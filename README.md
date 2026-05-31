# SubSurface — CityNerve

Predictive Infrastructure Intelligence for Toronto's Watermain Network.  
GPU-accelerated (NVIDIA RAPIDS) pipeline that predicts watermain failures, explains risk factors, and simulates cascade effects to optimize municipal capital expenditure.  
Built for the NVIDIA Spark Hackathon — Toronto.

---

## Prerequisites

Install these before running the demo stack:

| Requirement | Version / notes |
|-------------|-----------------|
| **Python** | 3.10+ (3.12 recommended on GX10) |
| **Node.js + npm** | 18+ (for the React UI) |
| **Ollama** | [ollama.com](https://ollama.com) — two local instances for AI workflows |
| **Mapbox token** | Free at [account.mapbox.com/access-tokens](https://account.mapbox.com/access-tokens/) |
| **GPU** (optional) | NVIDIA GPU for faster Whisper STT; CPU fallback works |

**Ollama models** — pull once before first run:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama pull nemotron-3-super:latest   # Workflow 2 (analysis)
OLLAMA_HOST=127.0.0.1:11436 ollama pull nemotron-nano:12b-v2    # Workflow 1 (summary + voice)
```

See [GX10-Nemotron-Ollama-Cheatsheet.md](GX10-Nemotron-Ollama-Cheatsheet.md) for dual-Ollama details on NVIDIA GX10.

---

## First-time setup

Run these commands once from the repo root:

```bash
cd SubSurface

# 1. Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Backend / LLM config
cp .env.example .env

# 3. React UI config — required for the 3D map
cp SubSurface-UI/.env.example SubSurface-UI/.env
```

Edit `SubSurface-UI/.env` and set your Mapbox token:

```bash
VITE_MAPBOX_TOKEN=pk.your_mapbox_token_here
```

The root `.env` defaults work for local development. See [Configuration](#configuration) if you need to change ports or LLM settings.

---

## Run the project

### Option A — Full demo stack (recommended)

One script starts everything: dual Ollama, FastAPI, React UI, and the Voice Reporting Line.

```bash
source .venv/bin/activate
./scripts/run_citynerve.sh
```

When startup finishes, open the URLs printed in the banner:

| Service | Default URL | Purpose |
|---------|-------------|---------|
| **React UI** | http://127.0.0.1:5173 | 3D map, pipe risk, W1/W2 AI agents |
| **FastAPI docs** | http://127.0.0.1:8000/docs | REST API |
| **Voice Reporting Line** | http://127.0.0.1:8504/client/ | Hold-to-talk caller simulation |
| **Ollama W2** | http://127.0.0.1:11434 | `nemotron-3-super:latest` (multi-role analysis) |
| **Ollama W1** | http://127.0.0.1:11436 | `nemotron-nano:12b-v2` (summaries + voice) |

Press **Ctrl+C** in the terminal to stop all services started by the script.

**Stop without starting:**

```bash
./scripts/run_citynerve.sh --stop
```

**Custom ports** (if defaults are busy):

```bash
FASTAPI_PORT=9000 UI_PORT=5174 VOICE_CHAT_PORT=8505 ./scripts/run_citynerve.sh
```

If the voice port is taken (common when Cursor forwards `:8503`/`:8504`), the script tries the next free port and prints the actual URL.

### Option B — Manual startup (separate terminals)

Use this when you want to run or debug services individually.

**Terminal 1 — Ollama (both workflows)**

```bash
./agent/scripts/ollama-dual-serve.example.sh
```

**Terminal 2 — FastAPI backend**

```bash
source .venv/bin/activate
export PYTHONPATH="$(pwd)"
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 3 — React UI**

```bash
cd SubSurface-UI
npm install          # first time only
npm run dev
```

**Terminal 4 — Voice Reporting Line (optional)**

```bash
./scripts/run_voice_chat.sh
```

Open http://127.0.0.1:5173 for the UI. The React app talks to FastAPI only — never to Ollama directly.

### Option C — API only (no UI, no voice)

Useful for testing endpoints without Node.js:

```bash
source .venv/bin/activate
export PYTHONPATH="$(pwd)"
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Try: http://127.0.0.1:8000/docs

---

## Verify it works

After startup, run the health check:

```bash
./agent/scripts/check_endpoints.sh
```

Quick API smoke test (synthetic data, no Ollama required for the pipe list):

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -s "http://127.0.0.1:8000/api/pipes?limit=3" | python3 -m json.tool
```

Workflow 1 with live LLM (select a pipe in the UI, or call the API):

```bash
curl -s "http://127.0.0.1:8000/api/pipes/WM-0001/risk-summary?use_real=false" | python3 -m json.tool
```

In the React UI: click a pipe on the map → **Workflow 1** summary loads in the sidebar.

---

## Configuration

### Root `.env` (backend + LLM)

Copy from `.env.example`. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WORKFLOW1_OPENAI_BASE_URL` | `http://127.0.0.1:11436/v1` | Ollama for summaries / voice |
| `WORKFLOW1_MODEL` | `nemotron-nano:12b-v2` | W1 model name |
| `WORKFLOW2_OPENAI_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama for multi-role analysis |
| `WORKFLOW2_MODEL` | `nemotron-3-super:latest` | W2 model name |
| `W2_PARALLEL` | `false` | Set `true` only if Ollama supports concurrent W2 calls |

Optional voice settings (also in `agent/.env.example`): `VOICE_TTS_ENGINE=kokoro` for spoken agent replies, `VOICE_WHISPER_DEVICE=cpu` if GPU memory is tight.

### `SubSurface-UI/.env` (React)

| Variable | Required | Purpose |
|----------|----------|---------|
| `VITE_MAPBOX_TOKEN` | **Yes** | Mapbox GL 3D map |
| `VITE_API_PROXY_TARGET` | No | FastAPI URL for Vite dev proxy (default `http://127.0.0.1:8000`) |
| `VITE_VOICE_CHAT_PORT` | No | Voice server port (default `8504`) |

---

## Voice Reporting Line

Simulates a live watermain-break call. Included in `./scripts/run_citynerve.sh`, or run alone:

```bash
./scripts/run_voice_chat.sh
```

**How to use:**

1. Open http://127.0.0.1:8504/client/ (allow microphone access).
2. **Hold** the mic button to speak; **release** to send.
3. Up to 3 exchanges with the agent (Whisper STT → Ollama W1).
4. Click **End call** to save the transcript to `voice_sessions/`.

The React UI listens for transcript events and can feed matched caller reports into Workflow 2.

Full voice docs: [agent/README.md](agent/README.md#voice-call-session)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **`ollama` not found** | Install from [ollama.com](https://ollama.com) or set `OLLAMA_BIN` |
| **`npm` not found** | Install Node.js 18+ or use [Option C — API only](#option-c--api-only-no-ui-no-voice) |
| **Port already in use** | Run `./scripts/run_citynerve.sh --stop`, or override ports (see above). If Cursor holds a port, stop the forward in the Ports panel. |
| **Map is blank** | Set `VITE_MAPBOX_TOKEN` in `SubSurface-UI/.env` and restart Vite |
| **LLM errors / timeouts** | Run `./agent/scripts/check_endpoints.sh`; confirm models are pulled |
| **Whisper CUDA error** (GX10/aarch64) | Rebuild CTranslate2 with CUDA — see [agent/README.md](agent/README.md#gx10-faster-whisper-cuda-setup) |
| **W2 analysis is slow** | Expected — five Super calls; allow several minutes |

Run agent tests:

```bash
source .venv/bin/activate
pytest agent/tests/ -v
```

---

## Agent + app stack

| Piece | Role | Port |
|-------|------|------|
| **model/** | XGBoost risk scoring | — |
| **backend/** (FastAPI) | REST API — pipes, W1/W2 via `agent.harness` | 8000 |
| **SubSurface-UI/** | React UI — 3D map, agents, voice alerts | 5173 |
| **Ollama W1** | Fast summaries (`nemotron-nano:12b-v2`) | 11436 |
| **Ollama W2** | Deep analysis (`nemotron-3-super:latest`) | 11434 |
| **Voice call** | Push-to-talk reporting line | 8504 |
| **`scripts/run_citynerve.sh`** | One command — full stack | — |
| **NemoClaw** | Agent sandboxes | [agent/nemoclaw/](agent/nemoclaw/) |

Details: [agent/README.md](agent/README.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

## Project structure

```text
SubSurface/
├── SubSurface-UI/   # React + Vite front-end (primary UI)
├── backend/         # FastAPI service
├── model/           # Risk / ML logic
├── agent/           # Ollama harness + W1/W2 gateways + voice bot
├── ml-models/       # GPU training pipeline (optional, separate from demo)
└── scripts/         # run_citynerve.sh, run_voice_chat.sh
```

## UI features (SubSurface-UI)

| Feature | Description |
|---------|-------------|
| 3D risk map | Mapbox GL map with risk-colored pipe segments |
| Filters + KPIs | Risk level, material, ward, pipe type, min risk score |
| Workflow 1 | Nemotron JSON risk summary on pipe select |
| Workflow 2 | Multi-role analysis (Engineer, Police, Field, Operations) + synthesis + BoM |
| Voice integration | Caller report alert, map marker, W2 transcript context |
| Critical queue | Top 100 critical pipes by network percentile |

## Tech stack

- **Data**: Open Data Toronto datasets fused via RAPIDS cuDF + cuSpatial
- **ML**: cuML XGBoost — P(break within 12 months) per pipe segment
- **Graph**: cuGraph — cascade failure propagation
- **Explainability**: cuML SHAP — feature contributions per prediction
- **Agent**: Nemotron via Ollama — natural language summaries and multi-role analysis
- **UI**: React + Mapbox GL (SubSurface-UI)
