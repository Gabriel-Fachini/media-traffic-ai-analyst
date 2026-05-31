from __future__ import annotations

import json
from typing import Any, Iterator

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
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


def test_query_debug_includes_turn_observability(
    client: TestClient,
) -> None:
    response = client.post(
        "/query",
        json={
            "question": (
                "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
            )
        },
        headers={"X-Debug": "true"},
    )
    body = QueryResponse.model_validate(response.json())

    assert response.status_code == 200
    assert body.metadata is not None
    assert body.metadata.debug is not None
    assert body.metadata.debug.observability is not None
    assert body.metadata.debug.observability.latency_ms is not None
    assert body.metadata.debug.observability.llm_call_count == 2
    assert body.metadata.debug.observability.tool_call_count == 1
    assert body.metadata.debug.observability.tools_used == ["traffic_volume_analyzer"]
    assert body.metadata.debug.observability.token_usage.input_tokens == 50
    assert body.metadata.debug.observability.token_usage.output_tokens == 32
    assert body.metadata.debug.observability.token_usage.total_tokens == 82


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
    assert body.debug.observability is not None
    assert body.debug.observability.latency_ms is not None


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
    assert body.debug.observability is not None
    assert body.debug.observability.tool_call_count == 1
    assert body.debug.observability.tools_used == ["channel_performance_analyzer"]


def test_query_rejects_blank_question_with_422(client: TestClient) -> None:
    response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422


def _parse_sse_events(raw_body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for block in raw_body.strip().split("\n\n"):
        if not block.strip():
            continue

        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))

        if event_name is None:
            continue

        payload = json.loads("\n".join(data_lines)) if data_lines else None
        events.append({"event": event_name, "data": payload})

    return events


def test_query_stream_emits_sse_events_for_tool_execution(
    client: TestClient,
) -> None:
    with client.stream(
        "POST",
        "/query/stream",
        json={
            "question": (
                "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
            )
        },
    ) as response:
        body = "".join(chunk for chunk in response.iter_text())

    events = _parse_sse_events(body)
    event_names = [event["event"] for event in events]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert event_names[0] == "metadata"
    assert "router" in event_names
    assert "tool_start" in event_names
    assert "tool_end" in event_names
    assert "token" in event_names
    assert event_names[-1] == "final"

    final_event = events[-1]["data"]
    assert final_event["answer"].startswith("SYNTH::traffic_volume_analyzer::")
    assert "traffic_volume_analyzer" in final_event["tools_used"]
    assert final_event["metadata"]["thread_id"]


def test_query_stream_emits_incremental_token_deltas_when_llm_streams() -> None:
    original_overrides = dict(app.dependency_overrides)

    class IncrementalStreamGraph:
        async def astream_events(
            self,
            state: dict[str, Any],
            config: dict[str, Any] | None = None,
            *,
            version: str,
            **kwargs: Any,
        ) -> Any:
            del config, version, kwargs
            question = state["question"]
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "agent"},
                "data": {"chunk": AIMessageChunk(content="Resposta ")},
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "metadata": {"langgraph_node": "agent"},
                "data": {"chunk": AIMessageChunk(content="incremental")},
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "question": question,
                        "final_answer": "Resposta incremental",
                        "tools_used": [],
                        "messages": [AIMessage(content="Resposta incremental")],
                    }
                },
            }

    app.dependency_overrides[get_query_graph] = lambda: IncrementalStreamGraph()
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            with test_client.stream(
                "POST",
                "/query/stream",
                json={"question": "Explique a resposta incremental"},
            ) as response:
                body = "".join(chunk for chunk in response.iter_text())
    finally:
        app.dependency_overrides = original_overrides

    events = _parse_sse_events(body)
    token_events = [event for event in events if event["event"] == "token"]

    assert response.status_code == 200
    assert [event["data"] for event in token_events] == [
        {"text_delta": "Resposta "},
        {"text_delta": "incremental"},
    ]
    assert events[-1]["data"]["answer"] == "Resposta incremental"


def test_query_stream_final_event_includes_debug_observability(
    client: TestClient,
) -> None:
    with client.stream(
        "POST",
        "/query/stream",
        json={
            "question": (
                "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
            )
        },
        headers={"X-Debug": "true"},
    ) as response:
        body = "".join(chunk for chunk in response.iter_text())

    events = _parse_sse_events(body)
    final_event = events[-1]["data"]
    debug_payload = final_event["metadata"]["debug"]

    assert response.status_code == 200
    assert events[-1]["event"] == "final"
    assert debug_payload["observability"]["latency_ms"] is not None
    assert debug_payload["observability"]["llm_call_count"] == 2
    assert debug_payload["observability"]["tool_call_count"] == 1
    assert debug_payload["observability"]["tools_used"] == ["traffic_volume_analyzer"]
    assert debug_payload["observability"]["token_usage"]["total_tokens"] == 82


def test_query_stream_emits_error_event_when_graph_times_out() -> None:
    original_overrides = dict(app.dependency_overrides)

    class TimeoutStreamGraph:
        async def astream_events(
            self,
            state: dict[str, Any],
            config: dict[str, Any] | None = None,
            *,
            version: str,
            **kwargs: Any,
        ) -> Any:
            del state, config, version, kwargs
            raise LlmTimeoutError(
                "simulated timeout",
                error_type="SimulatedTimeoutError",
                debug_message="simulated timeout",
            )
            yield  # pragma: no cover

    app.dependency_overrides[get_query_graph] = lambda: TimeoutStreamGraph()
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            with test_client.stream(
                "POST",
                "/query/stream",
                json={
                    "question": (
                        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
                    )
                },
                headers={"X-Debug": "true"},
            ) as response:
                body = "".join(chunk for chunk in response.iter_text())
    finally:
        app.dependency_overrides = original_overrides

    events = _parse_sse_events(body)

    assert response.status_code == 200
    assert [event["event"] for event in events] == ["metadata", "error"]
    assert events[-1]["data"]["detail"] == LLM_TIMEOUT_ERROR_MESSAGE
    assert events[-1]["data"]["debug"]["errors"][0]["error_type"] == "SimulatedTimeoutError"
    assert events[-1]["data"]["debug"]["observability"]["latency_ms"] is not None
