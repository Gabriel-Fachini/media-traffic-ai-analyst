from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable, cast

from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
import pytest

from app.clients.bigquery_client import BigQueryClient
from app.graph import build_tool_enabled_llm, invoke_analytics_graph
from app.main import app
from app.schemas.api import QueryResponse
from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput
from app.tools import channel_performance_analyzer, traffic_volume_analyzer
from app.utils.config import Settings


pytestmark = [pytest.mark.integration, pytest.mark.live]

JANUARY_START = date(2024, 1, 1)
JANUARY_END = date(2024, 1, 31)


def _require_bigquery_environment() -> None:
    credentials = Settings().google_application_credentials
    if not credentials:
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS nao configurada para testes live.")

    credentials_path = Path(credentials).expanduser().resolve()
    if not credentials_path.is_file():
        pytest.skip(
            "Arquivo de credenciais do GCP nao encontrado para testes live."
        )


def _require_llm_environment() -> None:
    settings = Settings()
    provider = settings.llm_provider
    if provider == "anthropic":
        api_key = settings.anthropic_api_key
        required_env = "ANTHROPIC_API_KEY"
    else:
        api_key = settings.openai_api_key
        required_env = "OPENAI_API_KEY"

    if not api_key:
        pytest.skip(f"{required_env} nao configurada para testes live.")


def _require_full_live_environment() -> None:
    _require_bigquery_environment()
    _require_llm_environment()


def test_live_bigquery_smoke() -> None:
    _require_bigquery_environment()

    result = BigQueryClient().smoke_test_thelook_dataset(
        start_date=JANUARY_START,
        end_date=JANUARY_END,
    )

    assert int(result["total_users"]) > 0


@pytest.mark.parametrize(
    ("label", "runner"),
    [
        (
            "traffic-volume-all",
            lambda: traffic_volume_analyzer(
                TrafficVolumeInput(start_date=JANUARY_START, end_date=JANUARY_END)
            ),
        ),
        (
            "traffic-volume-search",
            lambda: traffic_volume_analyzer(
                TrafficVolumeInput(
                    traffic_source="Search",
                    start_date=JANUARY_START,
                    end_date=JANUARY_END,
                )
            ),
        ),
        (
            "channel-performance-all",
            lambda: channel_performance_analyzer(
                ChannelPerformanceInput(
                    start_date=JANUARY_START,
                    end_date=JANUARY_END,
                )
            ),
        ),
        (
            "channel-performance-search",
            lambda: channel_performance_analyzer(
                ChannelPerformanceInput(
                    traffic_source="Search",
                    start_date=JANUARY_START,
                    end_date=JANUARY_END,
                )
            ),
        ),
    ],
)
def test_live_tools_execute_fixed_january_scenarios(
    label: str,
    runner: Callable[[], object],
) -> None:
    _require_bigquery_environment()
    result = cast(Any, runner())

    assert result.rows, f"{label} nao retornou linhas."
    if result.traffic_source is not None:
        assert all(row.traffic_source == result.traffic_source for row in result.rows)


def test_live_tool_binding_emits_tool_calls() -> None:
    _require_llm_environment()

    response = build_tool_enabled_llm().invoke(
        [
            HumanMessage(
                content=(
                    "Qual foi o volume de usuarios de Search entre "
                    "2024-01-01 e 2024-01-31?"
                )
            )
        ]
    )

    assert response.tool_calls
    assert response.tool_calls[0]["name"] == "traffic_volume_analyzer"


def test_live_graph_executes_end_to_end_query() -> None:
    _require_full_live_environment()

    state = invoke_analytics_graph(
        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
    )

    tools_used = cast(list[str], state.get("tools_used") or [])
    final_answer = cast(str, state.get("final_answer") or "")

    assert "channel_performance_analyzer" in tools_used
    assert final_answer.strip()


def test_live_api_query_preserves_thread_context() -> None:
    _require_full_live_environment()
    thread_id = "live-api-thread"

    with TestClient(app, raise_server_exceptions=False) as client:
        first_response = client.post(
            "/query",
            json={
                "question": (
                    "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
                ),
                "thread_id": thread_id,
            },
        )
        first_body = QueryResponse.model_validate(first_response.json())
        second_response = client.post(
            "/query",
            json={
                "question": "Como podemos melhorar esse canal?",
                "thread_id": thread_id,
            },
        )
        second_body = QueryResponse.model_validate(second_response.json())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_body.metadata is not None
    assert second_body.metadata is not None
    assert first_body.metadata.thread_id == thread_id
    assert second_body.metadata.thread_id == thread_id
    assert second_body.metadata.context_message_count > first_body.metadata.context_message_count
    assert second_body.answer.strip()
