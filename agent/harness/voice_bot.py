"""Standalone Firefox/Linux push-to-talk voice chat (default: Workflow 1).

The browser records speech while the user holds a button. On release, browser
uploads the audio clip, this FastAPI app transcribes it with local Whisper,
calls Ollama (W1 by default), synthesizes the response with server-side TTS,
and lets the browser play the generated WAV. Tapping **End call** writes the
transcript JSON to ``voice_sessions/`` (not after each turn).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_REPO_ROOT / "agent" / ".env")

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from agent.harness.client import chat
from agent.harness.endpoints import WorkflowProfile, get_chat_defaults, get_endpoint
from agent.harness.voice_transcript import write_messages_json

_VOICE_SYSTEM_PROMPT = """\
You are CityNerve Agent on Toronto's watermain break reporting line.
You are on a live voice call, taking notes to pass to emergency services and dispatch.
Speak as if you are writing down what the caller says: briefly acknowledge, then ask or confirm only what is still needed.

The call has at most 3 exchanges (caller speaks, you respond — three times total). After the third exchange you must stop asking questions, summarize the key facts you captured, and say you are passing the report to emergency services now.

Capture location (address or intersection), injuries or people at risk, and damage (flooding, road closure, vehicles stuck, etc.) when the caller provides them.
If someone may be seriously injured or in immediate danger, tell them to call 911 immediately, then keep noting details.
Never infer or invent incident details. If the caller did not provide a location, say you still need the location.
Keep each reply to 1-3 short sentences. Use plain language; stay calm and professional.
Reply in plain text only: no markdown, no asterisks, no bullet lists, no headings.
Do not start with labels like "Agent:" or "Assistant:" — speak directly to the caller.
Never output chat markup or special tokens (for example <|im_start|>, <|im_end|>, or role names like "user" / "assistant").
Do not invent pipe IDs, crew ETAs, or repair details.
"""

_AGENT_LABEL_RE = re.compile(
    r"^\s*(?:\*{1,2})?(?:Agent|Assistant)(?:\*{1,2})?\s*:\s*",
    re.IGNORECASE,
)
_CHAT_TEMPLATE_TOKEN_RE = re.compile(r"<\|[^>]*\|>", re.IGNORECASE)
_ROLE_ONLY_LINE_RE = re.compile(
    r"^\s*(?:user|assistant|system)\s*$",
    re.IGNORECASE,
)

_VOICE_MAX_TOKENS = int(os.getenv("VOICE_MAX_TOKENS", "3000"))
_VOICE_MAX_USER_TURNS = int(os.getenv("VOICE_MAX_USER_TURNS", "3"))
_VOICE_MIN_AUDIO_BYTES = int(os.getenv("VOICE_MIN_AUDIO_BYTES", "2048"))
_VOICE_NO_SPEECH_THRESHOLD = float(os.getenv("VOICE_NO_SPEECH_THRESHOLD", "0.6"))
_VOICE_JUNK_TRANSCRIPTS = {
    "you",
    "yeah",
    "yes",
    "no",
    "uh",
    "um",
    "hmm",
}
_CLOSING_REPLY = (
    "Thank you. I have recorded your report and am passing it to emergency services now. "
    "If anyone is in immediate danger, please stay on the line or call 911."
)
_EMPTY_REPLY_FALLBACK = (
    "I've noted what you said and I'm passing this to emergency services now."
)


def _strip_chat_template_leaks(text: str) -> str:
    """Remove Nemotron/Ollama chat-template tokens and leaked role blocks."""
    if not text:
        return ""
    marker = text.find("<|")
    if marker != -1:
        text = text[:marker]
    text = _CHAT_TEMPLATE_TOKEN_RE.sub("", text)
    kept: list[str] = []
    for line in text.splitlines():
        if _ROLE_ONLY_LINE_RE.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _plain_voice_reply(text: str) -> str:
    """Strip template leaks, markdown, and role labels for voice UI and TTS."""
    cleaned = _strip_chat_template_leaks(text)
    cleaned = _AGENT_LABEL_RE.sub("", cleaned)
    cleaned = re.sub(r"\*+", "", cleaned)
    return cleaned.strip()


def _is_low_information_transcript(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9'\s]", "", text.lower()).strip()
    if not normalized:
        return True
    words = normalized.split()
    return len(words) == 1 and normalized in _VOICE_JUNK_TRANSCRIPTS


def _user_turn_count(messages: list[dict[str, str]]) -> int:
    return sum(1 for message in messages if message.get("role") == "user")


def _turn_guidance(turn: int) -> str:
    if turn == 1:
        return (
            "Exchange 1 of 3: Note what they said for emergency services. "
            "Acknowledge briefly and ask one critical question (location, injuries, or severity)."
        )
    if turn == 2:
        return (
            "Exchange 2 of 3: Note what they just said. "
            "Ask only one remaining critical question if still needed."
        )
    return (
        "Exchange 3 of 3 (final): Summarize the key facts you captured, "
        "say you are passing the report to emergency services now, "
        "and do not ask further questions."
    )
_VOICE_OUTPUT_DIR = Path(
    os.getenv("VOICE_OUTPUT_DIR", str(_REPO_ROOT / "voice_sessions"))
).resolve()
_VOICE_DEBUG_AUDIO_DIR = _VOICE_OUTPUT_DIR / "debug_audio"
_VOICE_MODEL_CACHE_DIR = Path(
    os.getenv("VOICE_MODEL_CACHE_DIR", str(_REPO_ROOT / "voice_models"))
).resolve()
_DEFAULT_PORT = int(os.getenv("VOICE_CHAT_PORT", "8503"))


def _configure_model_caches() -> None:
    """Keep Whisper/Kokoro downloads under the repo (avoids ~/.cache permission issues)."""
    _VOICE_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    hf_home = Path(
        os.getenv("HF_HOME", str(_VOICE_MODEL_CACHE_DIR / "huggingface"))
    ).resolve()
    hf_home.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_home / "hub")


_configure_model_caches()
_WHISPER_MODEL_NAME = os.getenv("VOICE_WHISPER_MODEL", "base.en")
_WHISPER_DEVICE = os.getenv("VOICE_WHISPER_DEVICE", "cuda").strip().lower()
_WHISPER_COMPUTE_TYPE = os.getenv("VOICE_WHISPER_COMPUTE_TYPE", "float16").strip().lower()
_VOICE_TTS_ENGINE = os.getenv("VOICE_TTS_ENGINE", "none").strip().lower()
_VOICE_TTS_VOICE = os.getenv("VOICE_TTS_VOICE", "af_heart")
_VOICE_TTS_LANG_CODE = os.getenv("VOICE_TTS_LANG_CODE", "a")
_VOICE_TTS_DEVICE = os.getenv("VOICE_TTS_DEVICE", "cpu").strip().lower()
_VOICE_TTS_OUTPUT_DIR = _VOICE_OUTPUT_DIR / "tts_audio"
_VOICE_PIPER_MODEL = os.getenv("VOICE_PIPER_MODEL", "").strip()
_HOLD_MESSAGE_TURN1 = os.getenv(
    "VOICE_HOLD_MESSAGE",
    "I'm looking into this, let me get back to you in a moment.",
).strip()
_HOLD_MESSAGE_TURN2 = os.getenv(
    "VOICE_HOLD_MESSAGE_LATER",
    "Ok, let me note that down, please wait.",
).strip()
_HOLD_MESSAGE_TURN3 = os.getenv(
    "VOICE_HOLD_MESSAGE_TURN3",
    "Ok, we're almost done here, please bear with me.",
).strip()


def _hold_turn_key(turn: int) -> int:
    if turn <= 1:
        return 1
    if turn >= 3:
        return 3
    return 2


def _hold_message_text(turn: int) -> str:
    key = _hold_turn_key(turn)
    if key == 1:
        return _HOLD_MESSAGE_TURN1
    if key == 2:
        return _HOLD_MESSAGE_TURN2
    return _HOLD_MESSAGE_TURN3


def _server_tts_enabled() -> bool:
    return _VOICE_TTS_ENGINE not in {"", "none", "off", "disabled"}


def _hold_message_path(turn: int) -> Path:
    return _VOICE_TTS_OUTPUT_DIR / f"hold_message_turn{_hold_turn_key(turn)}.wav"


def _hold_message_text_path(turn: int) -> Path:
    return _VOICE_TTS_OUTPUT_DIR / f"hold_message_turn{_hold_turn_key(turn)}.txt"


def _voice_llm_profile() -> WorkflowProfile:
    raw = os.getenv("VOICE_LLM_PROFILE", "workflow1").strip().lower()
    if raw in {"workflow1", "w1", "1"}:
        return WorkflowProfile.WORKFLOW1
    if raw in {"workflow2", "w2", "2"}:
        return WorkflowProfile.WORKFLOW2
    raise ValueError(
        f"Invalid VOICE_LLM_PROFILE={raw!r}; use workflow1, workflow2, w1, or w2"
    )


_VOICE_LLM_PROFILE = _voice_llm_profile()
_whisper_model: Any | None = None
_kokoro_pipeline: Any | None = None

@dataclass
class VoiceSession:
    session_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[dict[str, str]] = field(
        default_factory=lambda: [{"role": "system", "content": _VOICE_SYSTEM_PROMPT}]
    )


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str


class EndSessionRequest(BaseModel):
    session_id: str


app = FastAPI(title="CityNerve Reporting Line")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
_sessions: dict[str, VoiceSession] = {}
_session_lock = asyncio.Lock()
_transcript_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()


def _broadcast_transcript_event(payload: dict[str, Any]) -> None:
    """Notify connected Streamlit browser listeners that a call transcript landed."""
    for queue in list(_transcript_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("Dropping transcript UI event for a slow subscriber")
            _transcript_subscribers.discard(queue)


def _cleanup_ephemeral_tts_files() -> None:
    """Remove per-turn reply clips; hold-message cache files are kept."""
    if not _VOICE_TTS_OUTPUT_DIR.is_dir():
        return
    for path in _VOICE_TTS_OUTPUT_DIR.glob("reply_*.wav"):
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not remove ephemeral TTS file {}: {}", path, exc)


@app.on_event("startup")
async def _warm_hold_message_audio() -> None:
    await asyncio.to_thread(_cleanup_ephemeral_tts_files)
    for turn in (1, 2, 3):
        try:
            path = await asyncio.to_thread(_ensure_hold_message_audio, turn)
            if path:
                logger.info("Hold message audio ready (turn {}): {}", turn, path)
        except Exception as exc:
            logger.warning("Hold message audio unavailable (turn {}): {}", turn, exc)


def _get_or_create_session(session_id: str | None) -> VoiceSession:
    sid = session_id or str(uuid4())
    if sid not in _sessions:
        _sessions[sid] = VoiceSession(session_id=sid)
    return _sessions[sid]


def _audio_suffix(content_type: str | None) -> str:
    content_type = content_type or ""
    if content_type.startswith("audio/ogg"):
        return ".ogg"
    if content_type.startswith("audio/wav"):
        return ".wav"
    if content_type.startswith("audio/mp4"):
        return ".m4a"
    return ".webm"


def _transcribe_audio_file(path: Path) -> str:
    """Transcribe one Firefox MediaRecorder clip with local faster-whisper."""
    global _whisper_model

    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _VOICE_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Loading faster-whisper model {} on {} ({}) from {}",
            _WHISPER_MODEL_NAME,
            _WHISPER_DEVICE,
            _WHISPER_COMPUTE_TYPE,
            _VOICE_MODEL_CACHE_DIR,
        )
        _whisper_model = WhisperModel(
            _WHISPER_MODEL_NAME,
            device=_WHISPER_DEVICE,
            compute_type=_WHISPER_COMPUTE_TYPE,
            download_root=str(_VOICE_MODEL_CACHE_DIR),
        )
        logger.info("faster-whisper ready")

    logger.info("Transcribing audio clip: {} bytes ({})", path.stat().st_size, path.suffix)
    segments, info = _whisper_model.transcribe(
        str(path),
        language="en",
        beam_size=5,
        vad_filter=True,
        no_speech_threshold=_VOICE_NO_SPEECH_THRESHOLD,
        condition_on_previous_text=False,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    logger.info(
        "WHISPER TRANSCRIPT ({:.2f}s, lang={}) -> {}",
        getattr(info, "duration", 0.0) or 0.0,
        getattr(info, "language", "unknown"),
        text,
    )
    if not text:
        _VOICE_DEBUG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        debug_path = _VOICE_DEBUG_AUDIO_DIR / (
            datetime.now(timezone.utc).strftime("empty_%Y%m%dT%H%M%SZ") + path.suffix
        )
        shutil.copy2(path, debug_path)
        logger.warning("Empty transcript; saved audio clip for inspection: {}", debug_path)
    elif _is_low_information_transcript(text):
        _VOICE_DEBUG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        debug_path = _VOICE_DEBUG_AUDIO_DIR / (
            datetime.now(timezone.utc).strftime("junk_%Y%m%dT%H%M%SZ") + path.suffix
        )
        shutil.copy2(path, debug_path)
        logger.warning(
            "Low-information transcript {!r}; saved audio clip for inspection: {}",
            text,
            debug_path,
        )
        return ""
    return text


def _load_kokoro_pipeline() -> Any:
    """Load Kokoro lazily so text-only chat still starts without TTS deps."""
    global _kokoro_pipeline

    if _kokoro_pipeline is None:
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro TTS is not installed. Install requirements or set "
                "VOICE_TTS_ENGINE=none."
            ) from exc

        logger.info(
            "Loading Kokoro TTS pipeline (lang_code={}, device={}, cache={})",
            _VOICE_TTS_LANG_CODE,
            _VOICE_TTS_DEVICE,
            os.environ.get("HUGGINGFACE_HUB_CACHE"),
        )
        _kokoro_pipeline = KPipeline(
            lang_code=_VOICE_TTS_LANG_CODE,
            repo_id="hexgrad/Kokoro-82M",
            device=_VOICE_TTS_DEVICE,
        )
        logger.info("Kokoro TTS ready")

    return _kokoro_pipeline


def _synthesize_with_kokoro(text: str, output_path: Path) -> None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "numpy and soundfile are required for Kokoro WAV output. Install requirements."
        ) from exc

    pipeline = _load_kokoro_pipeline()
    audio_parts = []
    sample_rate = 24000
    for _, _, audio in pipeline(text, voice=_VOICE_TTS_VOICE):
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        else:
            audio = np.asarray(audio)
        audio_parts.append(audio)

    if not audio_parts:
        raise RuntimeError("Kokoro produced no audio")

    if len(audio_parts) == 1:
        audio = audio_parts[0]
    else:
        audio = np.concatenate(audio_parts)

    sf.write(output_path, audio, sample_rate)


def _synthesize_with_piper(text: str, output_path: Path) -> None:
    piper = shutil.which("piper")
    if not piper:
        raise RuntimeError("Piper CLI not found on PATH")
    if not _VOICE_PIPER_MODEL:
        raise RuntimeError("VOICE_PIPER_MODEL must point to a Piper .onnx model")

    result = subprocess.run(
        [piper, "--model", _VOICE_PIPER_MODEL, "--output_file", str(output_path)],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Piper failed: {detail}")


def _synthesize_speech(text: str) -> Path:
    if _VOICE_TTS_ENGINE in {"", "none", "off", "disabled"}:
        raise RuntimeError("Local TTS is disabled")

    _VOICE_TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _VOICE_TTS_OUTPUT_DIR / (
        datetime.now(timezone.utc).strftime("reply_%Y%m%dT%H%M%S_%fZ") + ".wav"
    )

    if _VOICE_TTS_ENGINE == "kokoro":
        _synthesize_with_kokoro(text, output_path)
    elif _VOICE_TTS_ENGINE == "piper":
        _synthesize_with_piper(text, output_path)
    else:
        raise RuntimeError(
            f"Unsupported VOICE_TTS_ENGINE={_VOICE_TTS_ENGINE!r}; use kokoro, piper, or none"
        )

    return output_path


def _synthesize_speech_url(text: str) -> str | None:
    if _VOICE_TTS_ENGINE in {"", "none", "off", "disabled"}:
        return None

    try:
        audio_path = _synthesize_speech(text)
    except Exception as exc:
        logger.warning("Browser TTS audio skipped: {}", exc)
        return None

    logger.info("Generated browser TTS audio with {}: {}", _VOICE_TTS_ENGINE, audio_path)
    return f"/api/tts-audio/{audio_path.name}"


def _ensure_hold_message_audio(turn: int = 1) -> Path | None:
    """Synthesize a waiting-line clip once per turn variant and reuse it."""
    if _VOICE_TTS_ENGINE in {"", "none", "off", "disabled"}:
        return None
    path = _hold_message_path(turn)
    text = _hold_message_text(turn)
    text_path = _hold_message_text_path(turn)
    if path.exists() and path.stat().st_size > 0:
        try:
            if text_path.read_text(encoding="utf-8") == text:
                return path
        except OSError:
            pass

    _VOICE_TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Synthesizing hold message (turn {}): {!r}", turn, text)
    tmp_path = path.with_name(f"{path.stem}_{uuid4().hex}.tmp{path.suffix}")
    if _VOICE_TTS_ENGINE == "kokoro":
        _synthesize_with_kokoro(text, tmp_path)
    elif _VOICE_TTS_ENGINE == "piper":
        _synthesize_with_piper(text, tmp_path)
    else:
        return None
    tmp_path.replace(path)
    text_path.write_text(text, encoding="utf-8")
    return path


async def _respond_to_user_text(session_id: str | None, user_text: str) -> dict:
    profile = _VOICE_LLM_PROFILE
    endpoint = get_endpoint(profile)
    defaults = get_chat_defaults(profile)
    profile_label = profile.value.upper()

    async with _session_lock:
        session = _get_or_create_session(session_id)
        at_turn_limit = _user_turn_count(session.messages) >= _VOICE_MAX_USER_TURNS
        session.messages.append({"role": "user", "content": user_text})
        resolved_session_id = session.session_id
        user_turn = _user_turn_count(session.messages)
        messages_for_llm = list(session.messages)

    logger.info("USER TEXT (turn {}/{}) -> {}", user_turn, _VOICE_MAX_USER_TURNS, user_text)

    if at_turn_limit:
        reply = _CLOSING_REPLY
        logger.info("Max turns reached; using fixed closing reply")
    else:
        messages_for_llm.append(
            {"role": "system", "content": _turn_guidance(user_turn)}
        )
        logger.info(
            "SENDING TO {} ({}) turn {}/{} -> {}",
            profile_label,
            endpoint.model,
            user_turn,
            _VOICE_MAX_USER_TURNS,
            user_text,
        )
        raw_reply = await chat(
            profile,
            messages_for_llm,
            max_tokens=_VOICE_MAX_TOKENS,
            temperature=defaults.temperature,
        )
        reply = _plain_voice_reply(raw_reply)
        if not reply:
            logger.warning(
                "Empty reply after sanitizing; raw={!r}",
                raw_reply[:500] if raw_reply else raw_reply,
            )
            reply = _EMPTY_REPLY_FALLBACK
        elif reply != raw_reply:
            logger.debug("Sanitized reply: {!r} -> {!r}", raw_reply[:200], reply[:200])
        logger.info("{} RESPONSE -> {}", profile_label, reply)

    async with _session_lock:
        session = _get_or_create_session(resolved_session_id)
        session.messages.append({"role": "assistant", "content": reply})

    audio_url = await asyncio.to_thread(_synthesize_speech_url, reply)
    if audio_url:
        logger.info("TTS audio URL -> {}", audio_url)
    else:
        logger.warning("No TTS audio URL (engine={})", _VOICE_TTS_ENGINE)

    return {
        "session_id": session.session_id,
        "text": user_text,
        "response": reply,
        "model": endpoint.model,
        "audio_url": audio_url,
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/client/")


@app.get("/client/", response_class=HTMLResponse, include_in_schema=False)
def client() -> str:
    return _CLIENT_HTML.replace(
        "__HOLD_MESSAGES_JSON__",
        json.dumps(
            {
                1: _HOLD_MESSAGE_TURN1,
                2: _HOLD_MESSAGE_TURN2,
                3: _HOLD_MESSAGE_TURN3,
            }
        ),
    ).replace(
        "__SERVER_HOLD_AUDIO_ENABLED__",
        "true" if _server_tts_enabled() else "false",
    )


@app.get("/api/transcript-events")
async def api_transcript_events() -> StreamingResponse:
    """Server-sent events for Streamlit pages that should rerender on new calls."""

    async def stream():
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10)
        _transcript_subscribers.add(queue)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: transcript\ndata: {json.dumps(payload)}\n\n"
        finally:
            _transcript_subscribers.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat")
async def api_chat(body: ChatRequest) -> dict:
    user_text = body.text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="No speech text received")

    return await _respond_to_user_text(body.session_id, user_text)


@app.post("/api/chat-audio")
async def api_chat_audio(
    session_id: str | None = Form(default=None),
    audio: UploadFile = File(...),
) -> dict:
    suffix = _audio_suffix(audio.content_type)
    audio_bytes = await audio.read()
    if len(audio_bytes) < _VOICE_MIN_AUDIO_BYTES:
        logger.warning(
            "Audio clip too small for transcription: {} bytes ({})",
            len(audio_bytes),
            suffix,
        )
        raise HTTPException(
            status_code=400,
            detail="No usable audio was recorded. Click Start, speak, then click Send.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(audio_bytes)

    try:
        user_text = await asyncio.to_thread(_transcribe_audio_file, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not user_text:
        raise HTTPException(status_code=400, detail="No speech detected")

    return await _respond_to_user_text(session_id, user_text)


@app.post("/api/end")
async def api_end(body: EndSessionRequest) -> dict:
    """Write the call transcript JSON when the caller ends the session."""
    async with _session_lock:
        session = _sessions.pop(body.session_id, None)

    if session is None:
        session = VoiceSession(session_id=body.session_id)
        logger.info("End call with no server session; writing empty transcript")

    endpoint = get_endpoint(_VOICE_LLM_PROFILE)
    path = write_messages_json(
        messages=session.messages,
        output_dir=_VOICE_OUTPUT_DIR,
        session_id=session.session_id,
        started_at=session.started_at,
        model=endpoint.model,
        base_url=endpoint.base_url,
    )
    logger.info("Transcript saved on end call: {}", path)
    transcript_event = {
        "type": "voice_transcript_created",
        "session_id": session.session_id,
        "transcript_path": str(path),
        "filename": path.name,
        "mtime_ns": path.stat().st_mtime_ns,
    }
    _broadcast_transcript_event(transcript_event)
    return {
        "session_id": session.session_id,
        "path": str(path),
        "transcript_path": str(path),
    }


@app.api_route("/api/hold-audio", methods=["GET", "HEAD"], response_class=FileResponse)
async def api_hold_audio(turn: int = Query(default=1, ge=1, le=3)) -> FileResponse:
    path = await asyncio.to_thread(_ensure_hold_message_audio, turn)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Hold message audio not available")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.get("/api/tts-audio/{filename}", response_class=FileResponse)
async def api_tts_audio(filename: str) -> FileResponse:
    path = (_VOICE_TTS_OUTPUT_DIR / filename).resolve()
    if path.parent != _VOICE_TTS_OUTPUT_DIR.resolve() or path.suffix != ".wav":
        raise HTTPException(status_code=404, detail="Unknown audio file")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Unknown audio file")

    return FileResponse(path, media_type="audio/wav", filename=path.name)


_CLIENT_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>CityNerve Reporting Line</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: "SF Pro Display", Inter, system-ui, sans-serif;
      --bg-top: #0a1628;
      --bg-bottom: #02060f;
      --accent: #34d399;
      --accent-dim: #34d39933;
      --danger: #f43f5e;
      --danger-dim: #f43f5e44;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --glass: #ffffff0a;
      --border: #ffffff14;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100dvh;
      background: linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
      color: var(--text);
      display: flex;
      flex-direction: column;
      align-items: center;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }
    .phone {
      width: min(420px, 100vw);
      min-height: 100dvh;
      display: flex;
      flex-direction: column;
      padding: max(20px, env(safe-area-inset-top)) 24px max(28px, env(safe-area-inset-bottom));
    }
    .call-header {
      text-align: center;
      padding-top: 12px;
    }
    .call-label {
      font-size: 11px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 6px;
    }
    h1 {
      margin: 0;
      font-size: 1.35rem;
      font-weight: 600;
      letter-spacing: -0.02em;
    }
    .call-meta {
      margin-top: 8px;
      font-size: 0.9rem;
      color: var(--muted);
    }
    .call-meta.connected { color: var(--accent); }
    .call-meta.recording { color: var(--danger); }
    .call-meta.speaking { color: #60a5fa; }
    .call-meta.busy { color: #fbbf24; }
    .avatar-wrap {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 20px;
      min-height: 200px;
    }
    .avatar {
      width: 140px;
      height: 140px;
      border-radius: 50%;
      background: linear-gradient(145deg, #1e3a5f, #0f2744);
      border: 3px solid var(--border);
      display: grid;
      place-items: center;
      font-size: 2.5rem;
      font-weight: 700;
      color: var(--accent);
      box-shadow: 0 0 0 1px var(--border), 0 24px 48px #0006;
      position: relative;
    }
    .avatar::after {
      content: "";
      position: absolute;
      inset: -12px;
      border-radius: 50%;
      border: 2px solid transparent;
      transition: border-color 0.2s, transform 0.2s;
    }
    .avatar.pulse::after {
      border-color: var(--accent-dim);
      animation: ring 1.4s ease-out infinite;
    }
    .avatar.speaking::after {
      border-color: #60a5fa55;
      animation: ring 1s ease-out infinite;
    }
    @keyframes ring {
      0% { transform: scale(1); opacity: 1; }
      100% { transform: scale(1.15); opacity: 0; }
    }
    .caption {
      width: 100%;
      min-height: 72px;
      max-height: 140px;
      overflow-y: auto;
      text-align: center;
      font-size: 0.95rem;
      line-height: 1.45;
      color: var(--muted);
      padding: 0 8px;
    }
    .caption strong { color: var(--text); font-weight: 500; display: block; margin-bottom: 4px; }
    .caption.agent strong { color: #93c5fd; }
    .controls {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 28px;
      padding-bottom: 8px;
    }
    .talk-row {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 36px;
    }
    #talk {
      width: 88px;
      height: 88px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      background: var(--accent);
      color: #042f1a;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      box-shadow: 0 8px 32px var(--accent-dim);
      transition: transform 0.15s, background 0.15s;
    }
    #talk:active { transform: scale(0.94); }
    #talk:disabled { opacity: 0.4; cursor: wait; transform: none; }
    #talk.recording {
      background: var(--danger);
      color: #fff;
      box-shadow: 0 8px 32px var(--danger-dim);
    }
    #talk svg { width: 28px; height: 28px; fill: currentColor; }
    .call-btn {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      font-size: 9px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      background: var(--glass);
      border: 1px solid var(--border);
    }
    .call-btn svg { width: 22px; height: 22px; fill: currentColor; }
    #end {
      background: var(--danger);
      color: #fff;
      border-color: transparent;
    }
    #end svg { fill: #fff; }
    .transcript-toggle {
      background: none;
      border: none;
      color: var(--muted);
      font-size: 0.8rem;
      cursor: pointer;
      padding: 8px;
      margin-top: 4px;
    }
    .transcript {
      display: none;
      flex-direction: column;
      gap: 8px;
      max-height: 120px;
      overflow-y: auto;
      width: 100%;
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
    }
    .transcript.open { display: flex; }
    .transcript .line {
      font-size: 0.8rem;
      line-height: 1.35;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--glass);
    }
    .transcript .line.you { color: #cbd5e1; }
    .transcript .line.agent { color: #93c5fd; }
  </style>
</head>
<body>
  <div class="phone">
    <header class="call-header">
      <div class="call-label">Incoming call</div>
      <h1>CityNerve Reporting Line</h1>
      <div id="status" class="call-meta connected">Connected</div>
    </header>

    <section class="avatar-wrap">
      <div id="avatar" class="avatar" aria-hidden="true">CN</div>
      <div id="caption" class="caption">
        <span>Click Start, speak your report, then click Send.</span>
      </div>
    </section>

    <section class="controls">
      <div class="talk-row">
        <button id="end" class="call-btn" type="button" aria-label="End call">
          <svg viewBox="0 0 24 24"><path d="M12 9c-1.6 0-3 .5-3 3v4.5c0 .8.7 1.5 1.5 1.5H13v2.5h-2V21H7v-4H5c-1.1 0-2-.9-2-2V9c0-1.1.9-2 2-2h14c1.1 0 2 .9 2 2v6c0 1.1-.9 2-2 2h-2v-4h-2v2.5h1.5c.8 0 1.5-.7 1.5-1.5V12c0-2.5-1.4-3-3-3z"/></svg>
          End
        </button>
        <button id="talk" type="button" aria-label="Hold to speak">
          <svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"/></svg>
          <span id="talkLabel">Start</span>
        </button>
        <button id="toggleTranscriptBtn" class="call-btn" type="button" aria-label="Show transcript">
          <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2 5 5h-5V4zM8 12h8v2H8v-2zm0 4h5v2H8v-2z"/></svg>
          Log
        </button>
      </div>
      <button id="toggleTranscript" class="transcript-toggle" type="button">Show call log</button>
      <div id="log" class="transcript"></div>
    </section>
  </div>

  <script>
    const talk = document.getElementById("talk");
    const talkLabel = document.getElementById("talkLabel");
    const end = document.getElementById("end");
    const statusEl = document.getElementById("status");
    const logEl = document.getElementById("log");
    const captionEl = document.getElementById("caption");
    const avatarEl = document.getElementById("avatar");
    const toggleTranscript = document.getElementById("toggleTranscript");
    const toggleTranscriptBtn = document.getElementById("toggleTranscriptBtn");
    const HOLD_MESSAGES = __HOLD_MESSAGES_JSON__;
    const SERVER_HOLD_AUDIO_ENABLED = __SERVER_HOLD_AUDIO_ENABLED__;
    function holdTurnKey(turn) {
      if (turn <= 1) return 1;
      if (turn >= 3) return 3;
      return 2;
    }
    const sessionId = crypto.randomUUID();
    let processingTurn = 0;
    let recorder = null;
    let chunks = [];
    let stream = null;
    let holding = false;
    let sending = false;
    let recordingStartedAt = 0;
    let currentAudio = null;
    let holdAudio = null;
    const holdAudioAvailable = {};
    let callEnded = false;
    const MIN_CLIENT_AUDIO_BYTES = 2048;

    function setCallState(state, text) {
      statusEl.textContent = text;
      statusEl.className = "call-meta " + state;
      avatarEl.classList.remove("pulse", "speaking");
      if (state === "recording") avatarEl.classList.add("pulse");
      if (state === "speaking") avatarEl.classList.add("speaking");
    }
    function setCaption(label, text, who) {
      captionEl.innerHTML = "<strong>" + label + "</strong>" + text;
      captionEl.className = "caption" + (who ? " " + who : "");
    }
    function addMessage(role, text) {
      const div = document.createElement("div");
      div.className = "line " + (role === "user" ? "you" : "agent");
      div.textContent = (role === "user" ? "You: " : "Agent: ") + text;
      logEl.prepend(div);
      if (role === "user") {
        setCaption("You", text, "");
      } else {
        setCaption("Agent", text, "agent");
      }
    }
    function setTalkLabel(text) {
      talkLabel.textContent = text;
    }
    function describeBytes(bytes) {
      if (bytes < 1024) return bytes + " bytes";
      return (bytes / 1024).toFixed(1) + " KB";
    }
    function stopPlayback() {
      if (!currentAudio) return;
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
      avatarEl.classList.remove("speaking");
    }
    function stopHoldPlayback() {
      if (holdAudio) {
        holdAudio.pause();
        holdAudio.currentTime = 0;
        holdAudio = null;
      }
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    }
    function stopAllPlayback() {
      stopHoldPlayback();
      stopPlayback();
    }
    function holdMessageText(turn) {
      return HOLD_MESSAGES[holdTurnKey(turn)];
    }
    function holdAudioUrl(turn) {
      return "/api/hold-audio?turn=" + holdTurnKey(turn);
    }
    async function probeHoldAudio(turn) {
      if (!SERVER_HOLD_AUDIO_ENABLED) return false;
      const t = holdTurnKey(turn);
      if (t in holdAudioAvailable) return holdAudioAvailable[t];
      try {
        const res = await fetch(holdAudioUrl(t), { method: "HEAD", cache: "no-store" });
        holdAudioAvailable[t] = res.ok || res.status === 206;
      } catch {
        holdAudioAvailable[t] = false;
      }
      return holdAudioAvailable[t];
    }
    function speakHoldFallback(text) {
      if (!("speechSynthesis" in window)) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      window.speechSynthesis.speak(utterance);
    }
    async function playHoldMessage(turn) {
      const text = holdMessageText(turn);
      stopHoldPlayback();
      setCallState("busy", "One moment...");
      setCaption("Agent", text, "agent");
      avatarEl.classList.add("speaking");
      if (await probeHoldAudio(turn)) {
        holdAudio = new Audio(holdAudioUrl(turn));
        try {
          await holdAudio.play();
          holdAudio.onended = () => {
            if (sending) avatarEl.classList.remove("speaking");
          };
          return;
        } catch (err) {
          console.warn("Hold audio blocked:", err);
          holdAudio = null;
        }
      }
      speakHoldFallback(text);
    }
    function unlockAudio() {
      if (window._audioUnlocked) return;
      window._audioUnlocked = true;
      const silent = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQAAAAA=");
      silent.play().catch(() => {});
    }
    async function playAudio(url) {
      stopHoldPlayback();
      stopPlayback();
      if (!url) return false;
      currentAudio = new Audio(url);
      setCallState("speaking", "Agent speaking");
      avatarEl.classList.add("speaking");
      try {
        await currentAudio.play();
        currentAudio.onended = () => {
          avatarEl.classList.remove("speaking");
          if (!callEnded) setCallState("connected", "Connected");
        };
        return true;
      } catch (err) {
        console.warn("Autoplay blocked:", err);
        setCallState("connected", "Tap Hold to hear reply");
        const replay = () => {
          unlockAudio();
          currentAudio.play().then(() => setCallState("speaking", "Agent speaking")).catch((e) => {
            setCallState("connected", "Could not play audio");
          });
          talk.removeEventListener("pointerdown", replay);
        };
        talk.addEventListener("pointerdown", replay, { once: true });
        return false;
      }
    }
    function pickMimeType() {
      const candidates = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/ogg"
      ];
      return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
    }
    async function ensureMicStream() {
      if (stream) return stream;
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      const [track] = stream.getAudioTracks();
      console.info("Microphone track", track ? {
        label: track.label,
        enabled: track.enabled,
        muted: track.muted,
        readyState: track.readyState,
        settings: track.getSettings ? track.getSettings() : {}
      } : "none");
      return stream;
    }
    async function sendAudio(blob, durationMs) {
      if (!blob || blob.size === 0 || sending || callEnded) return;
      console.info("Recorded audio clip", { bytes: blob.size, durationMs });
      if (blob.size < MIN_CLIENT_AUDIO_BYTES) {
        setCallState("connected", "No audio captured");
        setCaption(
          "",
          "Recorded only " + describeBytes(blob.size) + " over " +
            (durationMs / 1000).toFixed(1) +
            "s. Check the browser microphone input, then click Start and try again.",
          ""
        );
        return;
      }
      sending = true;
      talk.disabled = true;
      processingTurn += 1;
      const holdPlayback = playHoldMessage(processingTurn);
      try {
        const form = new FormData();
        form.append("session_id", sessionId);
        form.append("audio", blob, blob.type.includes("webm") ? "speech.webm" : "speech.ogg");
        const res = await fetch("/api/chat-audio", { method: "POST", body: form });
        stopHoldPlayback();
        await holdPlayback.catch(() => {});
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        addMessage("user", data.text);
        addMessage("agent", data.response);
        if (data.audio_url) {
          await playAudio(data.audio_url);
        } else if (!callEnded) {
          setCallState("connected", "Connected");
          avatarEl.classList.remove("speaking");
        }
      } catch (err) {
        stopHoldPlayback();
        console.error(err);
        setCallState("connected", "Error — try again");
        setCaption("", err.message, "");
        avatarEl.classList.remove("speaking");
      } finally {
        talk.disabled = callEnded;
        if (!callEnded) setTalkLabel("Start");
        sending = false;
      }
    }
    async function startRecording(ev) {
      ev.preventDefault();
      if (callEnded) return;
      if (!navigator.mediaDevices || !window.MediaRecorder) {
        setCallState("connected", "Microphone unavailable");
        return;
      }
      if (sending || holding) return;
      stopAllPlayback();
      unlockAudio();
      try {
        const mic = await ensureMicStream();
        const [track] = mic.getAudioTracks();
        if (!track || track.readyState !== "live") {
          throw new Error("No live microphone input is available");
        }
        chunks = [];
        const mimeType = pickMimeType();
        recorder = new MediaRecorder(mic, mimeType ? { mimeType } : undefined);
        recorder.ondataavailable = (event) => {
          console.info("Recorder data chunk", event.data ? event.data.size : 0);
          if (event.data && event.data.size > 0) chunks.push(event.data);
        };
        recorder.onerror = (event) => {
          console.error("Recorder error", event.error || event);
        };
        recorder.onstop = () => {
          const type = recorder.mimeType || mimeType || "audio/ogg";
          const blob = new Blob(chunks, { type });
          const durationMs = recordingStartedAt ? Date.now() - recordingStartedAt : 0;
          recordingStartedAt = 0;
          sendAudio(blob, durationMs);
        };
        holding = true;
        recordingStartedAt = Date.now();
        talk.classList.add("recording");
        setTalkLabel("Send");
        setCallState("recording", "Listening...");
        setCaption("", "Recording... click Send when you are done speaking.", "");
        recorder.start(250);
      } catch (err) {
        console.error(err);
        setCallState("connected", "Microphone error");
      }
    }
    function stopRecording(ev) {
      if (ev) ev.preventDefault();
      if (!holding) return;
      holding = false;
      talk.classList.remove("recording");
      setTalkLabel("Start");
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.requestData();
        } catch {}
        recorder.stop();
      }
    }
    function toggleRecording(ev) {
      if (holding) {
        stopRecording(ev);
      } else {
        startRecording(ev);
      }
    }
    async function endSession() {
      if (callEnded) return;
      stopAllPlayback();
      if (holding) {
        holding = false;
        talk.classList.remove("recording");
        setTalkLabel("Start");
        if (recorder && recorder.state !== "inactive") recorder.stop();
      }
      callEnded = true;
      talk.disabled = true;
      setCallState("busy", "Ending call...");
      const res = await fetch("/api/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
      });
      if (res.ok) {
        await res.json();
        setCallState("connected", "Call ended");
        toggleTranscript.textContent = "Call ended";
        toggleTranscript.disabled = true;
      } else {
        callEnded = false;
        talk.disabled = false;
        const detail = await res.text();
        setCallState("connected", "Could not save transcript");
        setCaption("", detail || "End call failed.", "");
      }
    }
    function toggleLog() {
      const open = logEl.classList.toggle("open");
      const label = open ? "Hide call log" : "Show call log";
      toggleTranscript.textContent = label;
    }
    toggleTranscript.addEventListener("click", toggleLog);
    toggleTranscriptBtn.addEventListener("click", toggleLog);
    talk.addEventListener("click", toggleRecording);
    end.addEventListener("click", endSession);
    unlockAudio();
    if (SERVER_HOLD_AUDIO_ENABLED) {
      probeHoldAudio(1);
      probeHoldAudio(2);
      probeHoldAudio(3);
    }
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CityNerve Reporting Line")
    parser.add_argument("--host", default=os.getenv("VOICE_CHAT_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    args = parser.parse_args()

    print()
    print("CityNerve Reporting Line")
    print(f"   Open: http://{args.host}:{args.port}/client/")
    print(f"   Transcripts: {_VOICE_OUTPUT_DIR}/")
    llm = get_endpoint(_VOICE_LLM_PROFILE)
    print(f"   LLM: {_VOICE_LLM_PROFILE.value} ({llm.model} @ {llm.base_url})")
    print(f"   Browser TTS: {_VOICE_TTS_ENGINE}")
    print()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
