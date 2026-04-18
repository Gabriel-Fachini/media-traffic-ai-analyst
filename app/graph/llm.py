from __future__ import annotations

import asyncio
from typing import Any

import httpx
from anthropic import APITimeoutError as AnthropicAPITimeoutError
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import APITimeoutError as OpenAIAPITimeoutError
from pydantic import SecretStr

from app.graph.tools import get_analytics_tools
from app.utils.config import Settings, SettingsError, SupportedLlmProvider, get_settings

DEFAULT_LLM_TEMPERATURE = 0


class LlmTimeoutError(RuntimeError):
    """Raised when the underlying LLM provider times out."""


def is_llm_timeout_error(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            TimeoutError,
            asyncio.TimeoutError,
            httpx.TimeoutException,
            OpenAIAPITimeoutError,
            AnthropicAPITimeoutError,
        ),
    )


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


def _build_llm_with_optional_fallback(
    settings: Settings,
    *,
    bind_tools: bool,
) -> Any:
    def prepare_model(
        provider: SupportedLlmProvider,
        model_name: str,
    ) -> BaseChatModel | Any:
        model = _build_provider_model(settings, provider, model_name)
        if bind_tools:
            return _bind_analytics_tools(model)
        return model

    primary_model = prepare_model(settings.llm_provider, settings.llm_model)
    if not settings.llm_fallback_provider:
        return primary_model

    fallback_model_name = settings.llm_fallback_model
    if fallback_model_name is None:
        raise SettingsError(
            "LLM_FALLBACK_MODEL e obrigatorio quando um fallback estiver configurado."
        )

    fallback_model = prepare_model(settings.llm_fallback_provider, fallback_model_name)
    return primary_model.with_fallbacks([fallback_model])


def build_analytics_llm(settings: Settings | None = None) -> Any:
    """Build the base chat model used by the analytics graph, with optional fallback."""

    resolved_settings = _resolve_settings(settings)
    return _build_llm_with_optional_fallback(resolved_settings, bind_tools=False)


def build_tool_enabled_llm(settings: Settings | None = None) -> Any:
    """Build a chat model already bound to analytics tools, with optional fallback."""

    resolved_settings = _resolve_settings(settings)
    return _build_llm_with_optional_fallback(resolved_settings, bind_tools=True)
