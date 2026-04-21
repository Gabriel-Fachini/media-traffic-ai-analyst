from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.schemas.api import QueryRequest
from app.utils.config import Settings, SettingsError


pytestmark = pytest.mark.unit


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_FALLBACK_PROVIDER",
        "LLM_FALLBACK_MODEL",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(env_name, raising=False)


def _build_settings_for_test(**kwargs: object) -> Settings:
    settings_type = cast(Any, Settings)
    return settings_type(**kwargs)


def test_query_request_trims_question_and_normalizes_empty_thread_id() -> None:
    request = QueryRequest(question="  Quanto vendeu Search ontem?  ", thread_id="   ")

    assert request.question == "Quanto vendeu Search ontem?"
    assert request.thread_id is None


def test_query_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="   ")


def test_settings_require_complete_fallback_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_env(monkeypatch)

    with pytest.raises(ValidationError):
        _build_settings_for_test(
            _env_file=None,
            **{
                "OPENAI_API_KEY": "sk-test",
                "LLM_FALLBACK_MODEL": "gpt-4o-mini",
            }
        )


def test_settings_validate_environment_requires_existing_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_settings_env(monkeypatch)
    missing_credentials_path = tmp_path / "missing-service-account.json"
    settings = _build_settings_for_test(
        _env_file=None,
        **{
            "OPENAI_API_KEY": "sk-test",
            "GOOGLE_APPLICATION_CREDENTIALS": str(missing_credentials_path),
        }
    )

    with pytest.raises(SettingsError):
        settings.validate_environment()
