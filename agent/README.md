# Agent layer (harness + Workflow 1 + Workflow 2)

Shared Ollama client, dual-workflow profiles, and Nemotron gateways for FastAPI. GX10 dual-Ollama setup: [GX10-Nemotron-Ollama-Cheatsheet.md](../GX10-Nemotron-Ollama-Cheatsheet.md).

## Layout

```text
agent/
├── harness/              # settings, endpoints, client, health
│   ├── voice_bot.py      # standalone push-to-talk voice UI (port 8504)
│   └── voice_transcript.py
├── evidence.py           # W1 evidence packet from pipe row + SHAP
├── gateway.py            # W1 orchestration
├── w2_gateway.py         # W2 multi-role + synthesis
├── prompts/              # workflow1_system.txt, w2/*.txt
├── schemas.py            # Pydantic contracts
├── scripts/              # check_endpoints.sh, ollama-dual-serve.example.sh
└── nemoclaw/             # sandboxes: hackathon-w1, nemotron-3-super
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

React UI and FastAPI clients **never** call Ollama — only FastAPI (`:8000`).

## Workflow 1

`GET /api/pipes/{pipe_id}/risk-summary` — Summary Agent in SubSurface-UI when a pipe is selected.

Modules: `schemas.py`, `evidence.py`, `llm_client.py`, `gateway.py`, `template_summary.py`.

## Workflow 2

`POST /api/analysis-runs` with:

```json
{
  "pipe_id": "WM-0001",
  "use_real": false,
  "use_latest_voice_transcript": true,
  "transcript_path": null
}
```

1. Build `AnalysisPacket` from pipe row
2. If a ended voice call transcript matches this `pipe_id` (see below), run the **transcript triage orchestrator** (`prompts/w2/transcript_orchestrator_system.txt`) — one short Super call that returns per-role caller context JSON
3. Four parallel Super calls (Engineer, Police, Field, Operations) — each role system prompt receives only its orchestrator slice under `## Caller report — unverified field intelligence`
4. Synthesis → `final_summary.md` + `action_plan.json` (synthesis gets its own orchestrator slice)
5. Artifacts under `data/analysis_runs/{run_id}/`

### Voice transcript → W2 handoff

After **End call** on the Reporting Line (`voice_sessions/voice_transcript_*.json`), W2 does **not** auto-run. When you request a report:

- [`voice_pipe_match.py`](voice_pipe_match.py) semantically matches the spoken intersection/streets (and geo when available) to a pipe `street` in the dataset
- Match is attached only when `matched_pipe_id == pipe_id` for the analysis run (avoids wrong-call bleed)
- Street matching works best with **real** Toronto data (`use_real=true`); synthetic pipes have empty `street` — geo-only or no match

Risk Map: **Run multi-role analysis (Super)** — shows caller match banner when a transcript is available.

Overview **Generate Order Report** runs W2 once for the caller-matched pipe when that pipe is in the selected queue.

Set `W2_PARALLEL=false` for sequential roles if GPU memory is tight.

## Config

Copy [`.env.example`](../.env.example) to repo root `.env` (WORKFLOW1/2, `W2_PARALLEL`).

LLM sampling (`WORKFLOW1_MAX_TOKENS`, `WORKFLOW2_MAX_TOKENS`, `LLM_TEMPERATURE`) is defined in [`harness/settings.py`](harness/settings.py) only — not in prompt modules.

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

## Voice call session

Standalone **CityNerve Reporting Line** (`agent/harness/voice_bot.py`) — not part of the React UI or FastAPI. Callers report a watermain break; the agent takes notes for emergency dispatch over up to three spoken exchanges.

### Prerequisites

1. **Python venv** with dependencies installed:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   On this GX10/GB10 machine (`linux-aarch64`), the PyPI `ctranslate2`
   wheel can install as CPU-only. If voice transcription fails with
   `This CTranslate2 package was not compiled with CUDA support`, rebuild
   `ctranslate2` from source with CUDA enabled. See
   [GX10 faster-whisper CUDA setup](#gx10-faster-whisper-cuda-setup).

2. **Ollama Workflow 1** running for live calls (check with `./agent/scripts/check_endpoints.sh`):

   | Voice call workflow | Ollama port | Model |
   |---------------------|-------------|-------|
   | Workflow 1 | `:11436` | `nemotron-nano:12b-v2` |

   Workflow 2 (`nemotron-3-super:latest` on `:11434`) is reserved for summary/report workflows.

3. **`.env`** at repo root — copy from `agent/.env.example` if needed. Voice-related keys are at the bottom of that file.

### Run

```bash
./scripts/run_voice_chat.sh
```

Equivalent manual start:

```bash
export PYTHONPATH="$(pwd)"
.venv/bin/python agent/harness/voice_bot.py
```

Prefer `./scripts/run_voice_chat.sh` on the GX10. It adds the local
CTranslate2, CUDA, and cuDNN library paths needed by the CUDA-enabled
`ctranslate2` build.

The server prints the client URL, transcript directory, LLM profile, and TTS engine on startup. Default client URL:

**http://0.0.0.0:8504/client/** (open it from another machine as `http://<server-ip>:8504/client/`)

Override host/port with `VOICE_CHAT_HOST`, `VOICE_CHAT_PORT`, or CLI flags `--host` / `--port`.

### Using the call UI

1. Open the client URL in **Firefox** (or any browser with mic support).
2. Grant microphone permission.
3. **Hold** the mic button while speaking; **release** to send the clip.
4. The server transcribes with local **faster-whisper**, sends text to Ollama, and returns the agent reply (and optional TTS audio).
5. Repeat for up to **`VOICE_MAX_USER_TURNS`** exchanges (default 3). On the final turn the agent summarizes and closes the call.
6. Click **End call** to finish and save the transcript.

While waiting for the model, the browser plays a short hold message:

- **Turn 1:** *"I'm looking into this, let me get back to you in a moment."*
- **Turn 2:** *"Ok, let me note that down, please wait."*
- **Turn 3:** *"Ok, we're almost done here, please bear with me."*

Customize via `VOICE_HOLD_MESSAGE`, `VOICE_HOLD_MESSAGE_LATER`, and `VOICE_HOLD_MESSAGE_TURN3` in `.env`.

### What gets saved

| Artifact | When | Location |
|----------|------|----------|
| Transcript JSON | **End call** only | `voice_sessions/voice_transcript_<session>_<timestamp>.json` |
| Reply TTS WAV | During call (playback only) | `voice_sessions/tts_audio/reply_*.wav` — ephemeral, gitignored, cleaned on server restart |
| Hold-message cache | First use | `voice_sessions/tts_audio/hold_message_turn*.wav` — gitignored |

The transcript contains caller and agent turns (no system prompt), session metadata, model info, and an `incident.location` block when a spoken Toronto intersection can be mapped. See `agent/harness/voice_transcript.py`.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VOICE_CHAT_HOST` | `0.0.0.0` | Bind address |
| `VOICE_CHAT_PORT` | `8504` | HTTP port |
| `VOICE_TRANSCRIPT_EVENTS_URL` | same hostname as UI, port `8504` (or Vite proxy `/voice-events`) | Browser SSE URL for transcript-created events |
| `VOICE_OUTPUT_DIR` | `voice_sessions` | Transcript output directory |
| `VOICE_MAX_USER_TURNS` | `3` | Max caller exchanges |
| `VOICE_MAX_TOKENS` | `3000` | LLM reply token limit |
| `VOICE_WHISPER_MODEL` | `base.en` | faster-whisper model |
| `VOICE_WHISPER_DEVICE` | `cuda` | Whisper device (`cpu`, `cuda`, `auto`) |
| `VOICE_WHISPER_COMPUTE_TYPE` | `float16` | faster-whisper compute type |
| `VOICE_MODEL_CACHE_DIR` | `voice_models` | Whisper/Kokoro download cache |
| `VOICE_TTS_ENGINE` | `none` | `kokoro`, `piper`, or `none` |
| `VOICE_TTS_VOICE` | `af_heart` | Kokoro voice id |
| `VOICE_TTS_DEVICE` | `cpu` | Kokoro device — use `cpu` to avoid CUDA OOM with Ollama |
| `VOICE_PIPER_MODEL` | *(empty)* | Path to Piper `.onnx` model when using `piper` |
| `VOICE_HOLD_MESSAGE` | *(see .env.example)* | Hold line on turn 1 |
| `VOICE_HOLD_MESSAGE_LATER` | *(see .env.example)* | Hold line on turn 2 |
| `VOICE_HOLD_MESSAGE_TURN3` | *(see .env.example)* | Hold line on turn 3 |

### Spoken replies (optional)

With `VOICE_TTS_ENGINE=none` (default), replies appear as on-screen captions only.

For audio playback in the browser:

```bash
# in .env
VOICE_TTS_ENGINE=kokoro
VOICE_TTS_DEVICE=cpu
```

The server synthesizes each reply to a temporary WAV, serves it to the browser, and does not keep it in version control. Alternatively, set `VOICE_TTS_ENGINE=piper` and point `VOICE_PIPER_MODEL` at a Piper ONNX model.

### Troubleshooting

- **No speech detected** — speak longer; check mic permissions and input device.
- **Ollama errors** — confirm the profile's port is up: `./agent/scripts/check_endpoints.sh`
- **CUDA OOM** — set `VOICE_TTS_DEVICE=cpu` and/or `VOICE_WHISPER_DEVICE=cpu`
- **No hold audio** — hold clips require TTS enabled (`VOICE_TTS_ENGINE=kokoro` or `piper`); otherwise the browser falls back to Web Speech API text-to-speech
- **`This CTranslate2 package was not compiled with CUDA support`** — on this
  GX10/GB10 (`linux-aarch64`) setup, rebuild CTranslate2 with CUDA enabled as
  described below.

### GX10 faster-whisper CUDA setup

The voice line uses `faster-whisper`, which uses `ctranslate2` underneath.
On x86_64, PyPI commonly provides a CUDA-enabled `ctranslate2` wheel. On this
machine (`linux-aarch64`, NVIDIA GB10), a plain `pip install -r requirements.txt`
can replace the working build with a CPU-only wheel. The symptom is:

```text
ValueError: This CTranslate2 package was not compiled with CUDA support
```

Check the current environment:

```bash
./.venv/bin/python - <<'PY'
import ctranslate2

print("ctranslate2", ctranslate2.__version__)
for device in ["cpu", "cuda"]:
    try:
        print(device, ctranslate2.get_supported_compute_types(device))
    except Exception as exc:
        print(device, type(exc).__name__ + ":", exc)
PY
```

If `cuda` raises that error, rebuild and install CTranslate2 locally:

```bash
# From repo root.
mkdir -p .build/ctranslate2-cuda .build/python312-dev/debs .build/python312-dev/root

# Get Python 3.12 headers without requiring sudo.
cd .build/python312-dev/debs
apt-get download python3.12-dev libpython3.12-dev
for deb in *.deb; do dpkg-deb -x "$deb" ../root; done
cd ../../..

# Clone and build CTranslate2 with CUDA/cuDNN.
cd .build/ctranslate2-cuda
if [ ! -d CTranslate2 ]; then
  git clone --recursive --branch v4.7.2 https://github.com/OpenNMT/CTranslate2.git
fi
CUDNN_ROOT="$PWD/../../.venv/lib/python3.12/site-packages/nvidia/cudnn"
cmake -S CTranslate2 -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/install" \
  -DWITH_CUDA=ON \
  -DWITH_CUDNN=ON \
  -DWITH_MKL=OFF \
  -DWITH_OPENBLAS=OFF \
  -DWITH_RUY=ON \
  -DOPENMP_RUNTIME=COMP \
  -DCUDA_ARCH_LIST="8.6+PTX" \
  -DCUDNN_INCLUDE_DIR="$CUDNN_ROOT/include" \
  -DCUDNN_LIBRARIES="$CUDNN_ROOT/lib/libcudnn.so.9"
cmake --build build --parallel 4
cmake --install build

# Build and install the Python wrapper into this project's venv.
cd CTranslate2/python
PYDEV="$(pwd)/../../../python312-dev/root"
CT2_ROOT="$(pwd)/../../install"
INC="-I$PYDEV/usr/include/python3.12 -I$PYDEV/usr/include"
/home/asus/Desktop/SubSurface/.venv/bin/python -m pip install -r install_requirements.txt
rm -rf build dist
CTRANSLATE2_ROOT="$CT2_ROOT" \
  CFLAGS="$INC" \
  CPPFLAGS="$INC" \
  LDFLAGS="-L$PYDEV/usr/lib/aarch64-linux-gnu -Wl,-rpath,$CT2_ROOT/lib" \
  /home/asus/Desktop/SubSurface/.venv/bin/python setup.py bdist_wheel
/home/asus/Desktop/SubSurface/.venv/bin/python -m pip install --force-reinstall dist/*.whl
```

`scripts/run_voice_chat.sh` prepends the required library paths at startup:

- `.build/ctranslate2-cuda/install/lib`
- `/usr/local/cuda/lib64`
- `.venv/lib/python3.12/site-packages/nvidia/cudnn/lib`

Verify the final setup:

```bash
LD_LIBRARY_PATH=".build/ctranslate2-cuda/install/lib:.venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}" \
  ./.venv/bin/python - <<'PY'
from faster_whisper import WhisperModel

model = WhisperModel("base.en", device="cuda", compute_type="float16", download_root="voice_models")
print("WhisperModel CUDA load OK")
PY
```

## Ports

| Service | Default port |
|---------|--------------|
| FastAPI | 8000 |
| React UI (Vite) | 5173 |
| Voice call (Reporting Line) | 8504 |
| Ollama W2 | 11434 |
| Ollama W1 | 11436 |

## NemoClaw

See [nemoclaw/README.md](nemoclaw/README.md) and [nemoclaw/investigate.md](nemoclaw/investigate.md).
