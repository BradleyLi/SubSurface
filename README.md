# SubSurface — CityNerve

Predictive Infrastructure Intelligence for Toronto's Watermain Network.  
GPU-accelerated (NVIDIA RAPIDS) pipeline that predicts watermain failures, explains risk factors, and simulates cascade effects to optimize municipal capital expenditure.  
Built for the NVIDIA Spark Hackathon — Toronto.

## Quick start (one command)

After setup, start the full stack (dual Ollama, FastAPI, Streamlit UI, Voice Reporting Line):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Nemotron W1/W2 — root .env.example (WORKFLOW1/2); agent/.env.example adds NemoClaw ports
cp .env.example .env

./scripts/run_citynerve.sh
```

| Service | URL | Notes |
|---------|-----|--------|
| Streamlit UI | http://127.0.0.1:8501 | `app.py` + `pages/` — map, simulator, assistant |
| FastAPI | http://127.0.0.1:8000 | API docs at `/docs` |
| Voice Reporting Line | http://127.0.0.1:8503/client/ | Hold-to-talk mic; transcript on **End call** → `voice_sessions/` |
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
4. Streamlit UI (calls FastAPI only, not Ollama)
5. Voice Reporting Line (optional) — `./scripts/run_voice_chat.sh`

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
# Optional if you run API elsewhere:
# export CITYNERVE_API_URL="http://127.0.0.1:8000"
streamlit run app.py --server.port 8501
```

Voice only (separate from Streamlit/FastAPI):

```bash
./scripts/run_voice_chat.sh
```

Open **http://127.0.0.1:8503/client/** locally, or **http://<server-ip>:8503/client/** from another machine — allow the browser microphone, **hold** the mic button to speak, **release** to send (local Whisper STT). Click **End call** to write the transcript JSON under `voice_sessions/` (nothing is saved before end call). Streamlit pages subscribe to transcript events on the same hostname that served the frontend, port `8503`, unless `VOICE_TRANSCRIPT_EVENTS_URL` is set.

Verify Ollama: `./agent/scripts/check_endpoints.sh`

</details>

### Voice call session (optional)

Standalone **CityNerve Reporting Line** — simulates a live watermain-break call. Included in `./scripts/run_citynerve.sh` on port **8503**, or run alone via `./scripts/run_voice_chat.sh`.

**Prerequisites**

- Python venv with `pip install -r requirements.txt`
- Ollama running for the chosen workflow (default **Workflow 1** on `:11436`; set `VOICE_LLM_PROFILE=workflow2` for W2 on `:11434`)
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

There is no separate npm/React frontend. **UI** = Streamlit (`app.py`, `pages/`) plus shared Python modules in `frontend/` (imported by pages, not a second web server).

| Piece | Role | Port |
|-------|------|------|
| **XGBoost / model/** | Deterministic risk scoring | — |
| **backend/** (FastAPI) | API — train/predict, future W1/W2 LLM routes via `agent.harness` | 8000 |
| **app.py + pages/** + **frontend/** | Streamlit UI — map, simulator, assistant; HTTP to FastAPI only | 8501 |
| **Ollama W1** | Fast summaries (`nemotron-nano:12b-v2`) | 11436 |
| **Ollama W2** | Deep analysis (`nemotron-3-super:latest`) | 11434 |
| **Voice call** | Push-to-talk reporting line — browser mic, local Whisper STT, Ollama agent (W1 default), transcript JSON on end call | 8503 |
| **`scripts/run_citynerve.sh`** | One command — starts Ollama (if needed), FastAPI, Streamlit, voice line | — |
| **NemoClaw** | Agent sandboxes for investigation | see [agent/nemoclaw/](agent/nemoclaw/) |

Details: [agent/README.md](agent/README.md) · [GX10-Nemotron-Ollama-Cheatsheet.md](GX10-Nemotron-Ollama-Cheatsheet.md)

## Project Structure

```text
SubSurface/
├── frontend/        # shared Python modules for Streamlit pages (not a separate web app)
├── backend/         # FastAPI service
├── model/           # risk/model logic
├── agent/           # harness (Ollama client) + narrative helpers
├── app.py           # Streamlit main page (entrypoint)
├── pages/           # Streamlit multipage views
└── scripts/         # run_citynerve.sh (full stack), run_voice_chat.sh (voice only)
```

Notes:
- `app.py` and `pages/` stay at root to preserve Streamlit multipage discovery.
- `frontend/` holds reusable UI/helpers imported by `pages/`; it is not a standalone server.
- New model logic lives in `model/risk_profile.py`.
- New agent narrative logic lives in `agent/why_failing_agent.py`.

## UI Pages

| Page | Description |
|---|---|
| `app.py` | Command Center — KPIs, pipeline status, top critical pipes |
| `pages/1_Risk_Map.py` | Risk map — SHAP explainability, Workflow 2 multi-role analysis (W1 on Overview queue) |
| `pages/2_Decision_Engine.py` | Priority queue — ranked replacement list, cost-benefit analysis |
| `pages/3_Cascade_Simulator.py` | Cascade Failure Simulator — "If pipe X breaks, what goes down?" |
| `pages/4_AI_Assistant.py` | AI chat interface — NIM/Nemotron natural language Q&A |

## Tech Stack

- **Data**: 10+ Open Data Toronto datasets fused via RAPIDS cuDF + cuSpatial
- **ML**: cuML XGBoost — predicts P(break within 12 months) per pipe segment
- **Graph**: cuGraph — cascade failure propagation through pipe network
- **Explainability**: cuML SHAP — feature contributions per prediction
- **Agent**: NIM / Nemotron — natural language work orders and what-if analysis
- **UI**: Streamlit + Plotly
