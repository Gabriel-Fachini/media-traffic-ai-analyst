from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.graph.tools import get_analytics_tools
from app.utils.config import Settings, SettingsError, SupportedLlmProvider, get_settings

DEFAULT_LLM_TEMPERATURE = 0


def _resolve_settings(settings: Settings | None = None) -> Settings:
    """Return validated settings with runtime env applied."""

    if settings is None:
        return get_settings()

    settings.validate_environment()
    settings.apply_runtime_environment()
    return settings


def _build_provider_model(
    settings: Settings,
    provider: SupportedLlmProvider,
    model_name: str,
) -> BaseChatModel:
    if provider == "openai":
        openai_api_key = settings.openai_api_key
        if openai_api_key is None:
            raise SettingsError("Variavel obrigatoria ausente no ambiente: OPENAI_API_KEY.")

        return ChatOpenAI(
            model=model_name,
            temperature=DEFAULT_LLM_TEMPERATURE,
            api_key=SecretStr(openai_api_key),
        )
    if provider == "anthropic":
        anthropic_api_key = settings.anthropic_api_key
        if anthropic_api_key is None:
            raise SettingsError("Variavel obrigatoria ausente no ambiente: ANTHROPIC_API_KEY.")

        return ChatAnthropic(
            model_name=model_name,
            temperature=DEFAULT_LLM_TEMPERATURE,
            timeout=None,
            stop=None,
            api_key=SecretStr(anthropic_api_key),
        )
    raise SettingsError(f"Provider LLM nao suportado: {provider}.")


def _bind_analytics_tools(model: BaseChatModel) -> Any:
    return model.bind_tools(
        get_analytics_tools(),
        tool_choice="auto",
    )


def build_analytics_llm(settings: Settings | None = None) -> BaseChatModel:
    """Build the base chat model used by the analytics graph."""

    resolved_settings = _resolve_settings(settings)
    return _build_provider_model(
        resolved_settings,
        resolved_settings.llm_provider,
        resolved_settings.llm_model,
    )


def build_tool_enabled_llm(settings: Settings | None = None) -> Any:
    """Build a chat model already bound to analytics tools, with optional fallback."""

    resolved_settings = _resolve_settings(settings)

    primary_model = _bind_analytics_tools(
        _build_provider_model(
            resolved_settings,
            resolved_settings.llm_provider,
            resolved_settings.llm_model,
        )
    )
    if not resolved_settings.llm_fallback_provider:
        return primary_model

    fallback_model_name = resolved_settings.llm_fallback_model
    if fallback_model_name is None:
        raise SettingsError(
            "LLM_FALLBACK_MODEL e obrigatorio quando um fallback estiver configurado."
        )

    fallback_model = _bind_analytics_tools(
        _build_provider_model(
            resolved_settings,
            resolved_settings.llm_fallback_provider,
            fallback_model_name,
        )
    )
    return primary_model.with_fallbacks([fallback_model])
