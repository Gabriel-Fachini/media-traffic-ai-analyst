from __future__ import annotations

from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from app.graph.llm import LlmTimeoutError
from app.graph.workflow import TEMPORARY_TOOL_FAILURE_MESSAGE, ToolExecutionError
from app.main import LLM_TIMEOUT_ERROR_MESSAGE, app, get_query_graph
from app.schemas.api import ErrorResponse, QueryResponse
from tests.fakes import DeterministicGraphBundle, build_deterministic_graph_bundle


pytestmark = pytest.mark.integration


@pytest.fixture
def graph_bundle() -> DeterministicGraphBundle:
    return build_deterministic_graph_bundle()


@pytest.fixture
def client(graph_bundle: DeterministicGraphBundle) -> Iterator[TestClient]:
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_query_graph] = lambda: graph_bundle.graph
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides = original_overrides


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_query_generates_thread_metadata_and_uses_fake_graph(
    client: TestClient,
) -> None:
    response = client.post(
        "/query",
        json={
            "question": (
                "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
            )
        },
    )
    body = QueryResponse.model_validate(response.json())

    assert response.status_code == 200
    assert "traffic_volume_analyzer" in body.tools_used
    assert body.answer.startswith("SYNTH::traffic_volume_analyzer::")
    assert body.metadata is not None
    assert body.metadata.thread_id
    assert body.metadata.thread_id_source == "generated"
    assert body.metadata.context_message_count >= 1


def test_query_preserves_thread_id_and_context_between_turns(
    client: TestClient,
) -> None:
    thread_id = "api-thread"
    first_response = client.post(
        "/query",
        json={"question": "Qual foi a receita de Search?", "thread_id": thread_id},
    )
    second_response = client.post(
        "/query",
        json={
            "question": "Entre 2024-01-01 e 2024-01-31.",
            "thread_id": thread_id,
        },
    )
    first_body = QueryResponse.model_validate(first_response.json())
    second_body = QueryResponse.model_validate(second_response.json())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_body.metadata is not None
    assert second_body.metadata is not None
    assert first_body.metadata.thread_id == thread_id
    assert second_body.metadata.thread_id == thread_id
    assert first_body.metadata.thread_id_source == "provided"
    assert second_body.metadata.thread_id_source == "provided"
    assert second_body.metadata.context_message_count > first_body.metadata.context_message_count


def test_query_debug_includes_router_decision_and_resolved_question(
    client: TestClient,
) -> None:
    thread_id = "debug-thread"
    client.post(
        "/query",
        json={"question": "Qual foi a receita de Search?", "thread_id": thread_id},
    )
    response = client.post(
        "/query",
        json={
            "question": "Entre 2024-01-01 e 2024-01-31.",
            "thread_id": thread_id,
        },
        headers={"X-Debug": "true"},
    )
    body = QueryResponse.model_validate(response.json())

    assert response.status_code == 200
    assert body.metadata is not None
    assert body.metadata.debug is not None
    assert (
        body.metadata.debug.resolved_question
        == "Qual foi a receita de Search? Entre 2024-01-01 e 2024-01-31."
    )
    assert body.metadata.debug.router_intent == "channel_performance"
    assert body.metadata.debug.agent_tool_calls
    assert body.metadata.debug.agent_tool_calls[0].tool_name == "channel_performance_analyzer"
    assert body.metadata.debug.errors == []


def test_query_returns_structured_timeout_error_when_graph_times_out() -> None:
    original_overrides = dict(app.dependency_overrides)

    class TimeoutGraph:
        def invoke(
            self,
            state: dict[str, Any],
            config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del state, config
            raise LlmTimeoutError(
                "simulated timeout",
                error_type="SimulatedTimeoutError",
                debug_message="simulated timeout",
            )

    app.dependency_overrides[get_query_graph] = lambda: TimeoutGraph()
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.post(
                "/query",
                json={
                    "question": (
                        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
                    )
                },
                headers={"X-Debug": "true"},
            )
    finally:
        app.dependency_overrides = original_overrides

    body = ErrorResponse.model_validate(response.json())

    assert response.status_code == 500
    assert body.detail == LLM_TIMEOUT_ERROR_MESSAGE
    assert body.debug is not None
    assert body.debug.resolved_question == (
        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
    )
    assert body.debug.errors[0].error_type == "SimulatedTimeoutError"


def test_query_returns_structured_tool_error_when_graph_tool_execution_fails() -> None:
    original_overrides = dict(app.dependency_overrides)

    class ToolFailureGraph:
        def invoke(
            self,
            state: dict[str, Any],
            config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del state, config
            raise ToolExecutionError(
                TEMPORARY_TOOL_FAILURE_MESSAGE,
                error_type="BigQueryClientError",
                tool_name="channel_performance_analyzer",
                debug_message="Falha simulada no BigQuery.",
                resolved_question=(
                    "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
                ),
            )

    app.dependency_overrides[get_query_graph] = lambda: ToolFailureGraph()
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.post(
                "/query",
                json={
                    "question": (
                        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
                    )
                },
                headers={"X-Debug": "true"},
            )
    finally:
        app.dependency_overrides = original_overrides

    body = ErrorResponse.model_validate(response.json())

    assert response.status_code == 500
    assert body.detail == TEMPORARY_TOOL_FAILURE_MESSAGE
    assert body.debug is not None
    assert body.debug.resolved_question == (
        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
    )
    assert body.debug.errors[0].source == "tool_executor"
    assert body.debug.errors[0].error_type == "BigQueryClientError"
    assert body.debug.errors[0].tool_name == "channel_performance_analyzer"


def test_query_rejects_blank_question_with_422(client: TestClient) -> None:
    response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422
