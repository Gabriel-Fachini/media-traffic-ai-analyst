from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    pass


class Settings(BaseSettings):
    app_name: str = Field(default="Media Traffic AI Analyst", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    google_application_credentials: str | None = Field(
        default=None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

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

    @field_validator("openai_api_key")
    @classmethod
    def normalize_openai_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def validate_required_environment(self) -> None:
        missing_variables: list[str] = []

        if not self.google_application_credentials:
            missing_variables.append("GOOGLE_APPLICATION_CREDENTIALS")

        if not self.openai_api_key:
            missing_variables.append("OPENAI_API_KEY")

        if missing_variables:
            missing_text = ", ".join(missing_variables)
            raise SettingsError(
                f"Variaveis obrigatorias ausentes no .env: {missing_text}."
            )

        raw_credentials_path = self.google_application_credentials
        if raw_credentials_path is None:
            raise SettingsError(
                "Variavel obrigatoria ausente no .env: GOOGLE_APPLICATION_CREDENTIALS."
            )

        credentials_path = Path(raw_credentials_path).expanduser().resolve()
        if not credentials_path.is_file():
            raise SettingsError(
                "Arquivo de credenciais do GCP nao encontrado em "
                f"{credentials_path}. Use caminho absoluto ou relativo ao diretorio atual."
            )

        self.google_application_credentials = str(credentials_path.resolve())

    def apply_runtime_environment(self) -> None:
        if self.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                self.google_application_credentials
            )

        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_required_environment()
    settings.apply_runtime_environment()
    return settings
