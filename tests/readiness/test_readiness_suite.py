from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterator, Mapping, cast

from fastapi.testclient import TestClient
import pytest

from app.graph.router import INVALID_DATES_MESSAGE, build_router_decision
from app.graph.workflow import (
    MISSING_DATES_MESSAGE,
    invoke_analytics_graph,
)
from app.main import app, get_query_graph
from app.schemas.api import QueryResponse
from app.tools.channel_performance_analyzer import CHANNEL_PERFORMANCE_SQL
from app.tools.traffic_volume_analyzer import TRAFFIC_VOLUME_SQL
from tests.fakes import DeterministicGraphBundle, build_deterministic_graph_bundle


pytestmark = pytest.mark.readiness

REFERENCE_DATE = date(2026, 4, 20)


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


def _require_str(state: Mapping[str, Any], key: str) -> str:
    value = state.get(key)
    assert isinstance(value, str)
    return value


def _require_list(state: Mapping[str, Any], key: str) -> list[str]:
    value = state.get(key)
    assert isinstance(value, list)
    return cast(list[str], value)


def test_api_surface_covers_health_and_blank_payload(client: TestClient) -> None:
    health_response = client.get("/health")
    invalid_response = client.post("/query", json={"question": "   "})

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert invalid_response.status_code == 422


def test_api_surface_covers_thread_context_and_debug(client: TestClient) -> None:
    thread_id = "readiness-api-thread"

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
        headers={"X-Debug": "true"},
    )

    first_body = QueryResponse.model_validate(first_response.json())
    second_body = QueryResponse.model_validate(second_response.json())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_body.metadata is not None
    assert second_body.metadata is not None
    assert second_body.metadata.thread_id == thread_id
    assert second_body.metadata.context_message_count > first_body.metadata.context_message_count
    assert second_body.metadata.debug is not None
    assert (
        second_body.metadata.debug.resolved_question
        == "Qual foi a receita de Search? Entre 2024-01-01 e 2024-01-31."
    )
    assert second_body.metadata.debug.router_intent == "channel_performance"
    assert second_body.metadata.debug.agent_tool_calls
    assert (
        second_body.metadata.debug.agent_tool_calls[0].tool_name
        == "channel_performance_analyzer"
    )


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        (
            "Como foi o volume de usuarios vindos de Search no ultimo mes?",
            "traffic_volume_analyzer",
        ),
        (
            "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?",
            "channel_performance_analyzer",
        ),
        (
            "Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-01-31?",
            "channel_performance_analyzer",
        ),
    ],
)
def test_graph_core_queries_trigger_expected_tools(
    graph_bundle: DeterministicGraphBundle,
    question: str,
    expected_tool: str,
) -> None:
    state = invoke_analytics_graph(
        question,
        graph=graph_bundle.graph,
        thread_id=f"readiness-{expected_tool}",
    )

    assert expected_tool in _require_list(state, "tools_used")
    assert _require_str(state, "final_answer").startswith(f"SYNTH::{expected_tool}::")


def test_graph_merges_missing_dates_follow_up() -> None:
    graph_bundle = build_deterministic_graph_bundle()
    thread_id = "readiness-missing-dates-thread"

    first_state = invoke_analytics_graph(
        "Qual foi a receita de Search?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "Entre 2024-01-01 e 2024-01-31.",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )

    assert _require_str(first_state, "final_answer") == MISSING_DATES_MESSAGE
    assert (
        _require_str(second_state, "resolved_question")
        == "Qual foi a receita de Search? Entre 2024-01-01 e 2024-01-31."
    )
    assert "channel_performance_analyzer" in _require_list(second_state, "tools_used")


def test_graph_asks_metric_clarification_before_tool_call() -> None:
    graph_bundle = build_deterministic_graph_bundle()

    state = invoke_analytics_graph(
        "Como o Search performou ontem?",
        graph=graph_bundle.graph,
        thread_id="readiness-ambiguous-thread",
    )

    assert "volume de usuarios ou performance financeira" in _require_str(
        state, "final_answer"
    )
    assert _require_list(state, "tools_used") == []


@pytest.mark.parametrize(
    ("follow_up_answer", "expected_tool"),
    [
        ("volume de usuarios", "traffic_volume_analyzer"),
        ("receita", "channel_performance_analyzer"),
    ],
)
def test_graph_preserves_temporal_context_after_metric_clarification(
    follow_up_answer: str,
    expected_tool: str,
) -> None:
    graph_bundle = build_deterministic_graph_bundle()
    thread_id = f"readiness-metric-choice-{expected_tool}"

    invoke_analytics_graph(
        "Como o Search performou ontem?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        follow_up_answer,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )

    assert (
        _require_str(second_state, "resolved_question")
        == f"Como o Search performou ontem? {follow_up_answer}"
    )
    assert expected_tool in _require_list(second_state, "tools_used")


@pytest.mark.parametrize(
    ("follow_up_question", "expected_intent"),
    [
        ("O que explica essa concentracao?", "diagnostic_follow_up"),
        ("Quais acoes devemos priorizar agora?", "strategy_follow_up"),
    ],
)
def test_graph_follow_ups_do_not_regress_to_out_of_scope(
    follow_up_question: str,
    expected_intent: str,
) -> None:
    graph_bundle = build_deterministic_graph_bundle()
    thread_id = expected_intent

    invoke_analytics_graph(
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        follow_up_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )

    router_decision = cast(dict[str, Any] | None, second_state.get("router_decision"))
    assert isinstance(router_decision, dict)
    assert router_decision["intent"] == expected_intent
    assert router_decision["refusal_reason"] is None
    assert _require_list(second_state, "tools_used") == []
    assert _require_str(second_state, "final_answer") == f"FOLLOW_UP::{follow_up_question}"


def test_router_guardrails_cover_scope_metric_dimension_and_invalid_ranges() -> None:
    out_of_scope = build_router_decision("Me conta uma piada", reference_date=REFERENCE_DATE)
    unsupported_metric = build_router_decision(
        "Qual foi o ROAS de Search ontem?",
        reference_date=REFERENCE_DATE,
    )
    unsupported_dimension = build_router_decision(
        "Qual campanha deu mais lucro no Facebook ontem?",
        reference_date=REFERENCE_DATE,
    )
    invalid_single_date = build_router_decision(
        "Qual foi a receita de Search em 31/02/2026?",
        reference_date=REFERENCE_DATE,
    )
    inverted_range = build_router_decision(
        "Qual foi a receita de Search entre 2024-02-10 e 2024-01-10?",
        reference_date=REFERENCE_DATE,
    )

    assert out_of_scope.intent == "out_of_scope"
    assert out_of_scope.refusal_reason == "out_of_scope"
    assert unsupported_metric.intent == "out_of_scope"
    assert unsupported_metric.refusal_reason == "unsupported_metric"
    assert unsupported_dimension.intent == "out_of_scope"
    assert unsupported_dimension.refusal_reason == "unsupported_dimension"
    assert invalid_single_date.clarification_reason == "invalid_dates"
    assert invalid_single_date.response_message == INVALID_DATES_MESSAGE
    assert inverted_range.clarification_reason == "invalid_dates"
    assert inverted_range.response_message == INVALID_DATES_MESSAGE


@pytest.mark.parametrize(
    ("question", "expected_start_date", "expected_end_date"),
    [
        (
            "Usuarios de Search entre 2024-01-01 e 2024-01-31",
            date(2024, 1, 1),
            date(2024, 1, 31),
        ),
        (
            "Usuarios de Search entre 01/01/2024 e 31/01/2024",
            date(2024, 1, 1),
            date(2024, 1, 31),
        ),
        (
            "Usuarios de Search entre 01/01/24 e 31/01/24",
            date(2024, 1, 1),
            date(2024, 1, 31),
        ),
        (
            "Receita de Search ontem",
            date(2026, 4, 19),
            date(2026, 4, 19),
        ),
        (
            "Volume de trafego este mes",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Receita por canal no ultimo mes",
            date(2026, 3, 1),
            date(2026, 3, 31),
        ),
        (
            "Usuarios nos ultimos 7 dias",
            date(2026, 4, 14),
            date(2026, 4, 20),
        ),
    ],
)
def test_router_resolves_all_priority_date_formats(
    question: str,
    expected_start_date: date,
    expected_end_date: date,
) -> None:
    decision = build_router_decision(question, reference_date=REFERENCE_DATE)

    assert decision.normalized_params.start_date == expected_start_date
    assert decision.normalized_params.end_date == expected_end_date
    assert decision.clarification_reason is None
    assert decision.refusal_reason is None


class _FakeBigQueryClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[Any] | None]] = []

    def run_query(
        self,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((sql, parameters))
        return self.rows


def _parameter_map(parameters: list[Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for parameter in parameters:
        payload = parameter.to_api_repr()
        mapped[payload["name"]] = {
            "type": payload["parameterType"]["type"],
            "value": payload["parameterValue"]["value"],
        }
    return mapped


def test_tool_sql_contracts_remain_parameterized_and_mvp_scoped() -> None:
    assert "`bigquery-public-data.thelook_ecommerce.users`" in TRAFFIC_VOLUME_SQL
    assert "@start_date" in TRAFFIC_VOLUME_SQL
    assert "@end_date" in TRAFFIC_VOLUME_SQL
    assert "@traffic_source" in TRAFFIC_VOLUME_SQL

    assert "`bigquery-public-data.thelook_ecommerce.users` u" in CHANNEL_PERFORMANCE_SQL
    assert "`bigquery-public-data.thelook_ecommerce.orders` o" in CHANNEL_PERFORMANCE_SQL
    assert "`bigquery-public-data.thelook_ecommerce.order_items` oi" in CHANNEL_PERFORMANCE_SQL
    assert "COUNT(DISTINCT o.order_id)" in CHANNEL_PERFORMANCE_SQL
    assert "ROUND(SUM(CAST(oi.sale_price AS NUMERIC)), 2)" in CHANNEL_PERFORMANCE_SQL
    assert "@start_date" in CHANNEL_PERFORMANCE_SQL
    assert "@end_date" in CHANNEL_PERFORMANCE_SQL
    assert "@traffic_source" in CHANNEL_PERFORMANCE_SQL


def test_tools_pass_parameterized_queries_to_bigquery_client() -> None:
    from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput
    from app.tools.channel_performance_analyzer import channel_performance_analyzer
    from app.tools.traffic_volume_analyzer import traffic_volume_analyzer

    traffic_client = _FakeBigQueryClient(
        rows=[{"traffic_source": "Search", "user_count": 10}]
    )
    performance_client = _FakeBigQueryClient(
        rows=[
            {
                "traffic_source": "Search",
                "total_orders": 7,
                "total_revenue": "1234.56",
            }
        ]
    )

    traffic_result = traffic_volume_analyzer(
        TrafficVolumeInput(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        bq_client=cast(Any, traffic_client),
    )
    performance_result = channel_performance_analyzer(
        ChannelPerformanceInput(
            traffic_source="Search",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        bq_client=cast(Any, performance_client),
    )

    traffic_sql, traffic_params = traffic_client.calls[0]
    performance_sql, performance_params = performance_client.calls[0]

    assert traffic_sql == TRAFFIC_VOLUME_SQL
    assert _parameter_map(cast(list[Any], traffic_params)) == {
        "start_date": {"type": "DATE", "value": "2024-01-01"},
        "end_date": {"type": "DATE", "value": "2024-01-31"},
        "traffic_source": {"type": "STRING", "value": None},
    }
    assert traffic_result.rows[0].user_count == 10

    assert performance_sql == CHANNEL_PERFORMANCE_SQL
    assert _parameter_map(cast(list[Any], performance_params)) == {
        "start_date": {"type": "DATE", "value": "2024-01-01"},
        "end_date": {"type": "DATE", "value": "2024-01-31"},
        "traffic_source": {"type": "STRING", "value": "Search"},
    }
    assert performance_result.rows[0].total_revenue == Decimal("1234.56")
