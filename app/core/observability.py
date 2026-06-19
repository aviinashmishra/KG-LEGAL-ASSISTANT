"""Optional tracing: LangSmith + Arize Phoenix. No-ops unless configured."""
from __future__ import annotations

import os

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("kg-legal.obs")


def init_observability() -> dict:
    settings = get_settings()
    status = {"langsmith": False, "phoenix": False}

    if settings.langsmith_api_key.strip():
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", "kg-legal-rag")
        status["langsmith"] = True
        logger.info("LangSmith tracing enabled")

    if settings.phoenix_enabled:
        try:
            import phoenix as px  # type: ignore

            px.launch_app()
            status["phoenix"] = True
            logger.info("Arize Phoenix launched")
        except Exception as exc:  # pragma: no cover
            logger.info(f"Phoenix not available: {exc}")

    return status
