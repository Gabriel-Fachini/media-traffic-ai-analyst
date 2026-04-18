from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    pass


SupportedLlmProvider = Literal["openai", "anthropic"]


class Settings(BaseSettings):
    app_name: str = Field(default="Media Traffic AI Analyst", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    google_application_credentials: str | None = Field(
        default=None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
    )
    llm_provider: SupportedLlmProvider = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_fallback_provider: SupportedLlmProvider | None = Field(
        default=None,
        alias="LLM_FALLBACK_PROVIDER",
    )
    llm_fallback_model: str | None = Field(default=None, alias="LLM_FALLBACK_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("google_application_credentials")
    @classmethod
    def normalize_credentials_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "llm_fallback_model",
    )
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("llm_model")
    @classmethod
    def normalize_llm_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("LLM_MODEL nao pode ser vazio.")
        return cleaned

    @model_validator(mode="after")
    def validate_fallback_pair(self) -> Settings:
        if self.llm_fallback_provider and not self.llm_fallback_model:
            raise ValueError(
                "LLM_FALLBACK_MODEL e obrigatorio quando LLM_FALLBACK_PROVIDER for definido."
            )
        if self.llm_fallback_model and not self.llm_fallback_provider:
            raise ValueError(
                "LLM_FALLBACK_PROVIDER e obrigatorio quando LLM_FALLBACK_MODEL for definido."
            )
        return self

    def require_provider_api_key(self, provider: SupportedLlmProvider) -> None:
        if provider == "openai" and not self.openai_api_key:
            raise SettingsError(
                "Variavel obrigatoria ausente no ambiente: OPENAI_API_KEY."
            )
        if provider == "anthropic" and not self.anthropic_api_key:
            raise SettingsError(
                "Variavel obrigatoria ausente no ambiente: ANTHROPIC_API_KEY."
            )

    def validate_environment(self) -> None:
        self.require_provider_api_key(self.llm_provider)
        if self.llm_fallback_provider:
            self.require_provider_api_key(self.llm_fallback_provider)

        if self.google_application_credentials:
            credentials_path = (
                Path(self.google_application_credentials).expanduser().resolve()
            )
            if not credentials_path.is_file():
                raise SettingsError(
                    "Arquivo de credenciais do GCP nao encontrado em "
                    f"{credentials_path}. Verifique a configuracao no ambiente."
                )
            self.google_application_credentials = str(credentials_path.resolve())

    def apply_runtime_environment(self) -> None:
        if self.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                self.google_application_credentials
            )

        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key

        if self.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_environment()
    settings.apply_runtime_environment()
    return settings
