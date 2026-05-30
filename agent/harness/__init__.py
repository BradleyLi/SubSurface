"""Shared Ollama client and workflow profile config for FastAPI / Streamlit."""

from .client import chat
from .endpoints import WorkflowProfile, get_chat_defaults, get_endpoint
from .health import check_all, check_profile
from .workflow1 import (
    JsonTable,
    TABLE_CASCADE_IMPACT,
    TABLE_NETWORK_CONTEXT,
    TABLE_PIPE_PROFILE,
    TABLE_RISK_DRIVERS,
    TABLE_SHAP,
    build_w1_messages,
    summarize,
)

__all__ = [
    "JsonTable",
    "TABLE_CASCADE_IMPACT",
    "TABLE_NETWORK_CONTEXT",
    "TABLE_PIPE_PROFILE",
    "TABLE_RISK_DRIVERS",
    "TABLE_SHAP",
    "WorkflowProfile",
    "build_w1_messages",
    "chat",
    "check_all",
    "check_profile",
    "get_chat_defaults",
    "get_endpoint",
    "summarize",
]
