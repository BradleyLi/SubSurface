"""Environment-backed settings for dual Ollama workflow profiles."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class HarnessSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _REPO_ROOT / "agent" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    workflow1_openai_base_url: str = "http://127.0.0.1:11436/v1"
    workflow1_model: str = "nemotron-nano:12b-v2"
    workflow1_context_window: int = 128_000  # Nemotron-Nano 12B v2 (+ VL variant): 128K tokens
    workflow1_max_tokens: int = 3000
    workflow1_temperature: float = 0.3

    workflow2_openai_base_url: str = "http://127.0.0.1:11434/v1"
    workflow2_model: str = "nemotron-3-super:latest"
    workflow2_max_tokens: int = 3000
    workflow2_temperature: float = 0.3
    openai_api_key: str = "ollama"

    nemoclaw_w1_sandbox: str = "hackathon-w1"
    nemoclaw_w2_sandbox: str = "nemotron-3-super"

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    streamlit_port: int = 8501


@lru_cache
def get_settings() -> HarnessSettings:
    return HarnessSettings()
