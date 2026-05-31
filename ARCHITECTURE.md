# SubSurface / CityNerve — System Architecture

**SubSurface** (branded **CityNerve**) is a predictive infrastructure-intelligence platform for
Toronto's watermain network, built for the NVIDIA Spark Hackathon. It combines a GPU ML pipeline
(RAPIDS / XGBoost / SHAP), geospatial data fusion from Toronto Open Data, dual local LLM workflows
(Nemotron via Ollama), a Streamlit dashboard, and an optional push-to-talk voice reporting line.

## Service topology

| Service | Port | Entry point | Role |
|---------|------|-------------|------|
| Streamlit UI | 8501 | `app.py` + `pages/` | Dashboard: risk map, decision engine, cascade sim, AI assistant |
| FastAPI backend | 8000 | `backend/main.py` | Data + AI workflow API (Streamlit talks here, never to Ollama directly) |
| Voice Reporting Line | 8503 | `agent/harness/voice_bot.py` | Push-to-talk caller intake (Whisper STT + Ollama + optional TTS) |
| Ollama W1 | 11436 | `nemotron-nano:12b-v2` | Fast JSON risk summaries, voice agent, neighbourhood match |
| Ollama W2 | 11434 | `nemotron-3-super:latest` | Multi-role deep analysis, synthesis, procurement |

One-command startup: `./scripts/run_citynerve.sh`. Offline ML pipeline: `ml-models/run_pipeline.sh`
(separate conda `rapids-26.04` env).

## System architecture

![SubSurface system architecture](docs/architecture.png)

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart TB
    subgraph clients["Clients (Browser)"]
        direction LR
        BrowserUI["Streamlit Dashboard<br/>(rendered HTML/Plotly)"]
        VoiceUI["Voice Reporting Line UI<br/>(embedded HTML + vanilla JS,<br/>MediaRecorder + fetch)"]
    end

    subgraph streamlit["Streamlit UI · :8501 (app.py + pages/)"]
        direction TB
        Pages["Pages: Risk Map · Decision Engine ·<br/>Cascade Sim · AI Assistant · Watermains"]
        FE["frontend/ helpers<br/>nav · workflow1_ui · report · order_report_ui"]
        Styles["app_styles.py (injected CSS)"]
        APIClient["api_client.py<br/>(urllib → REST, in-process fallback)"]
        VoiceMatch["agent/voice_pipe_match.py<br/>(transcript → pipe overlay)"]
        Pages --> FE --> APIClient
        Pages --> VoiceMatch
    end

    subgraph backend["FastAPI Backend · :8000 (backend/main.py)"]
        direction TB
        Health["/health, /health/workflow1|2"]
        PipesAPI["/api/pipes, /api/watermains-layer"]
        W1API["/api/pipes/{id}/risk-summary (W1)"]
        W2API["/api/analysis-runs (W2)"]
        AIAPI["/api/ai-response (rule-based)"]
    end

    subgraph agent["Agent Layer"]
        direction TB
        GW1["gateway.py · Workflow 1<br/>evidence → JSON summary"]
        GW2["w2_gateway.py · Workflow 2<br/>4 roles + synthesis"]
        Orch["w2_orchestrator.py<br/>(transcript triage)"]
        Proc["procurement/<br/>catalog · selection · BOM"]
        Schemas["schemas.py (Pydantic contracts)"]
        GW2 --> Orch
        GW2 --> Proc
    end

    subgraph harness["Harness (shared LLM infra)"]
        direction LR
        Client["client.py (async httpx)"]
        Endpoints["endpoints.py · settings.py"]
        HealthChk["health.py"]
    end

    subgraph voice["Voice Bot · :8503 (agent/harness/voice_bot.py)"]
        direction TB
        VBApi["/api/chat-audio, /api/chat,<br/>/api/end, /api/tts-audio"]
        Whisper["faster-whisper (local STT)"]
        TTS["Kokoro / Piper TTS (optional)"]
        VT["voice_transcript.py<br/>(JSON + location extraction)"]
        VBApi --> Whisper
        VBApi --> TTS
        VBApi --> VT
    end

    subgraph llm["Dual Ollama (local LLM)"]
        direction LR
        OllamaW1["W1 · :11436<br/>nemotron-nano:12b-v2"]
        OllamaW2["W2 · :11434<br/>nemotron-3-super"]
    end

    subgraph stores["File-based Persistence"]
        direction LR
        VS[("voice_sessions/*.json")]
        AR[("data/analysis_runs/")]
        MLP[("ml-models/.structured-data/<br/>predictions *.jsonl")]
        ProcData[("data/procurement/*.json")]
        Geo[("neighbourhoods geojson")]
    end

    subgraph external["External (runtime)"]
        direction LR
        CKAN["Toronto Open Data<br/>(CKAN GeoJSON)"]
        HF["Hugging Face Hub<br/>(Whisper/Kokoro weights)"]
    end

    subgraph mlpipe["ML Pipeline (offline · conda RAPIDS)"]
        direction LR
        DL["download_data.py"] --> Parquet["build_structured_parquet.py"]
        Parquet --> Train["train_xgb_gpu.py"]
        Train --> Predict["predict_xgb_gpu.py"]
    end

    BrowserUI -->|HTTP| streamlit
    VoiceUI -->|fetch multipart/JSON| VBApi

    APIClient -->|REST JSON| backend

    PipesAPI --> DataLayer["data_utils · real_data · ml_predictions"]
    W1API --> GW1
    W2API --> GW2

    GW1 --> Client
    GW2 --> Client
    Orch --> Client
    Proc --> Client
    HealthChk --> OllamaW1
    Client --> OllamaW1
    Client --> OllamaW2
    Client --> Endpoints

    VBApi --> Client

    DataLayer --> CKAN
    DataLayer --> MLP
    Whisper -.first use.-> HF
    TTS -.first use.-> HF
    Proc --> ProcData
    VoiceMatch --> Geo

    VT --> VS
    VoiceMatch -.reads.-> VS
    GW2 --> AR
    Predict --> MLP
    Predict -.offline.-> CKAN
    DataLayer -.fallback in-process.-> agent
```

</details>

## Request flows

![SubSurface request flows](docs/flows.png)

<details>
<summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    autonumber
    actor Caller
    actor Engineer
    participant Voice as Voice Bot :8503
    participant W1 as Ollama W1
    participant FS as voice_sessions/
    participant UI as Streamlit :8501
    participant API as FastAPI :8000
    participant GW2 as w2_gateway
    participant W2 as Ollama W2

    Note over Caller,W1: Voice intake (independent service)
    Caller->>Voice: Hold-to-talk audio
    Voice->>Voice: faster-whisper STT
    Voice->>W1: chat (Nemotron Nano)
    W1-->>Voice: agent reply (+ optional TTS)
    Caller->>Voice: End call
    Voice->>FS: write voice_transcript_*.json

    Note over Engineer,W2: Analyst reviews & runs deep analysis
    Engineer->>UI: open Risk Map
    UI->>API: GET /api/pipes
    API-->>UI: pipe DataFrame (Toronto + ML risk)
    UI->>FS: find_pipe_for_latest_transcript()
    FS-->>UI: matched pipe → map overlay
    Engineer->>UI: Run multi-role analysis
    UI->>API: POST /api/analysis-runs
    API->>GW2: workflow2_run(pipe_id)
    GW2->>W2: transcript orchestrator + procurement
    GW2->>W2: 4 role reports (parallel) + synthesis
    W2-->>GW2: role reports + action plan + BOM
    GW2->>GW2: save to data/analysis_runs/
    GW2-->>UI: structured result → UI tabs
```

</details>

## Key characteristics

- **Three runtime services** (Streamlit, FastAPI, Voice Bot). Streamlit never calls Ollama
  directly — it routes through FastAPI, with an in-process fallback if the API is unreachable.
- **Two LLM workflows on dual Ollama**: W1 (Nemotron Nano) for fast JSON summaries and the voice
  agent; W2 (Nemotron Super) for 4-role + synthesis analysis, transcript orchestration, and procurement.
- **The harness** (`agent/harness/`) is the shared async LLM infrastructure every caller routes through.
- **Voice → analysis handoff**: the voice bot writes transcript JSON; `voice_pipe_match` geocodes
  and street-matches it to a pipe, overlays a caller report on the map, and optionally feeds Workflow 2.
- **Local-first / no cloud**: all inference is local Ollama; persistence is entirely files. The only
  external runtime calls are Toronto Open Data (CKAN) and Hugging Face (first-time model weights).
- **Offline ML pipeline** (conda RAPIDS env) trains XGBoost on GPU and emits prediction JSONL the
  app joins onto live pipe data at runtime.
