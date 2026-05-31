from __future__ import annotations

import os
from functools import lru_cache

from app.infra.config import Settings


def apply_runtime_environment(settings: Settings) -> None:
    """Propagate settings values into os.environ for SDK auto-configuration."""
    if settings.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
            settings.google_application_credentials
        )

    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    if settings.langchain_tracing_v2 and settings.langchain_api_key and settings.langchain_project:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_environment()
    apply_runtime_environment(settings)
    return settings
