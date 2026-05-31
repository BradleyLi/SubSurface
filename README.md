# SubSurface — CityNerve

Predictive Infrastructure Intelligence for Toronto's Watermain Network.  
GPU-accelerated (NVIDIA RAPIDS) pipeline that predicts watermain failures, explains risk factors, and simulates cascade effects to optimize municipal capital expenditure.  
Built for the NVIDIA Spark Hackathon — Toronto.

## Quick start (one command)

After setup, start the full stack (dual Ollama, FastAPI, React UI, Voice Reporting Line):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Nemotron W1/W2 — root .env.example (WORKFLOW1/2); agent/.env.example adds NemoClaw ports
cp .env.example .env
cp SubSurface-UI/.env.example SubSurface-UI/.env   # set VITE_MAPBOX_TOKEN

./scripts/run_citynerve.sh
```

For the demo stack with FastAPI on `:9000`, run:

```bash
FASTAPI_PORT=9000 ./scripts/run_citynerve.sh
```

If a requested port is busy, the script automatically picks the next available
port. Open the `Voice Reporting` URL printed in the startup banner, for example
`http://localhost:8504/client/`.

The Voice Reporting Line always uses Workflow 1. Workflow 2 is reserved for
multi-role analysis in the React UI.

| Service | URL | Notes |
|---------|-----|--------|
| React UI (Vite) | http://127.0.0.1:5173 | `SubSurface-UI/` — 3D map, W1/W2 agents, voice alerts |
| FastAPI | http://127.0.0.1:8000 | API docs at `/docs` |
| Voice Reporting Line | http://127.0.0.1:8504/client/ | Hold-to-talk mic; transcript on **End call** → `voice_sessions/` |
| Ollama W2 | http://127.0.0.1:11434 | `nemotron-3-super:latest` |
| Ollama W1 | http://127.0.0.1:11436 | `nemotron-nano:12b-v2` |

Health check (after startup): `./agent/scripts/check_endpoints.sh`

**Workflow 1 PoC:** `GET /api/pipes/{pipe_id}/risk-summary?use_real=false` — Nemotron JSON summary from local evidence packet.

<details>
<summary><strong>Manual startup</strong> (terminals / partial stack)</summary>

**Start order on GX10 (full demo with local LLMs):**

1. Dual Ollama — W2 `:11434`, W1 `:11436` ([cheatsheet](GX10-Nemotron-Ollama-Cheatsheet.md)) — `./agent/scripts/ollama-dual-serve.example.sh`
2. NemoClaw sandboxes `hackathon-w1` + `nemotron-3-super` ([agent/nemoclaw/README.md](agent/nemoclaw/README.md))
3. FastAPI backend
4. React UI (`SubSurface-UI/`) — calls FastAPI only, not Ollama
5. Voice Reporting Line (optional) — `./scripts/run_voice_chat.sh`

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd SubSurface-UI && npm install && npm run dev
```

Voice only (separate from React/FastAPI):

```bash
./scripts/run_voice_chat.sh
```

Open **http://127.0.0.1:8504/client/** locally, or **http://<server-ip>:8504/client/** from another machine — allow the browser microphone, **hold** the mic button to speak, **release** to send (local Whisper STT). Click **End call** to write the transcript JSON under `voice_sessions/` (nothing is saved before end call). The React UI listens for transcript events and refreshes the caller-report alert via `/api/voice/match/latest`.

Verify Ollama: `./agent/scripts/check_endpoints.sh`

</details>

### Voice call session (optional)

Standalone **CityNerve Reporting Line** — simulates a live watermain-break call. Included in `./scripts/run_citynerve.sh` on port **8504**, or run alone via `./scripts/run_voice_chat.sh`.

**Prerequisites**

- Python venv with `pip install -r requirements.txt`
- Ollama Workflow 1 running on `:11436`; Workflow 2 is reserved for multi-role analysis
- Firefox or another browser with microphone access

GX10/GB10 note: if voice transcription fails with
`This CTranslate2 package was not compiled with CUDA support`, the
`linux-aarch64` Python environment needs the local CUDA-enabled CTranslate2
build documented in [agent/README.md](agent/README.md#gx10-faster-whisper-cuda-setup).

**During the call**

1. Allow microphone access when prompted.
2. **Hold** the mic button to speak; **release** to send. Whisper transcribes locally; the agent replies via Ollama.
3. Up to **3 exchanges** (caller speaks, agent responds). While the model is thinking, the agent plays a short hold line (first turn: *"I'm looking into this…"*; later turns: *"Ok, let me note that down."*).
4. Click **End call** when finished. That writes the transcript JSON to `voice_sessions/` — nothing is saved before end call.

**Optional: spoken replies**

Set `VOICE_TTS_ENGINE=kokoro` in `.env` for natural local TTS playback in the browser. Use `VOICE_TTS_DEVICE=cpu` if GPU memory is tight while Ollama is loaded. Leave `VOICE_TTS_ENGINE=none` for text-only captions.

Full env reference and troubleshooting: [agent/README.md](agent/README.md#voice-call-session).

## Agent + app stack

Primary UI is **SubSurface-UI** (React + Vite + Mapbox GL). The React app calls FastAPI only — never Ollama directly.

| Piece | Role | Port |
|-------|------|------|
| **XGBoost / model/** | Deterministic risk scoring | — |
| **backend/** (FastAPI) | API — pipes, W1/W2 LLM routes via `agent.harness` | 8000 |
| **SubSurface-UI/** | React UI — 3D map, W1 summary, W2 multi-role analysis, voice alerts | 5173 |
| **Ollama W1** | Fast summaries (`nemotron-nano:12b-v2`) | 11436 |
| **Ollama W2** | Deep analysis (`nemotron-3-super:latest`) | 11434 |
| **Voice call** | Push-to-talk reporting line — browser mic, local Whisper STT, Ollama agent (W1 default), transcript JSON on end call | 8504 |
| **`scripts/run_citynerve.sh`** | One command — starts Ollama (if needed), FastAPI, React UI, voice line | — |
| **NemoClaw** | Agent sandboxes for investigation | see [agent/nemoclaw/](agent/nemoclaw/) |

Details: [agent/README.md](agent/README.md) · [GX10-Nemotron-Ollama-Cheatsheet.md](GX10-Nemotron-Ollama-Cheatsheet.md)

## Project Structure

```text
SubSurface/
├── SubSurface-UI/   # React + Vite front-end (primary UI)
├── backend/         # FastAPI service
├── model/           # risk/model logic
├── agent/           # harness (Ollama client) + narrative helpers
└── scripts/         # run_citynerve.sh (full stack), run_voice_chat.sh (voice only)
```

Notes:
- New model logic lives in `model/risk_profile.py`.
- Agent narrative logic lives in `agent/gateway.py` (W1) and `agent/w2_gateway.py` (W2).

## UI Features (SubSurface-UI)

| Feature | Description |
|---|---|
| 3D risk map | Mapbox GL map with risk-colored pipe segments |
| Filters + KPIs | Risk level, material, ward, pipe type, min risk score |
| Workflow 1 | Nemotron JSON risk summary on pipe select |
| Workflow 2 | Multi-role analysis (Engineer, Police, Field, Operations) + synthesis + BoM |
| Voice integration | Caller report alert, map marker, W2 transcript context |
| Critical queue | Top 100 critical pipes by network percentile |

## Tech Stack

- **Data**: 10+ Open Data Toronto datasets fused via RAPIDS cuDF + cuSpatial
- **ML**: cuML XGBoost — predicts P(break within 12 months) per pipe segment
- **Graph**: cuGraph — cascade failure propagation through pipe network
- **Explainability**: cuML SHAP — feature contributions per prediction
- **Agent**: NIM / Nemotron — natural language work orders and what-if analysis
- **UI**: React + Mapbox GL (SubSurface-UI)
