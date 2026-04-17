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

    def validate_environment(self) -> None:
        if not self.openai_api_key:
            raise SettingsError(
                "Variavel obrigatoria ausente no ambiente: OPENAI_API_KEY."
            )

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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_environment()
    settings.apply_runtime_environment()
    return settings
