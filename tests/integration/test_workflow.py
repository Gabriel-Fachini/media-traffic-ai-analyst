from __future__ import annotations

from typing import cast

import pytest

from app.graph.workflow import (
    AnalyticsGraphState,
    MISSING_DATES_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    invoke_analytics_graph,
)
from app.schemas.router import RouterDecision
from tests.fakes import DeterministicGraphBundle, build_deterministic_graph_bundle


pytestmark = pytest.mark.integration


@pytest.fixture
def graph_bundle() -> DeterministicGraphBundle:
    return build_deterministic_graph_bundle()


def _require_str(state: AnalyticsGraphState, key: str) -> str:
    value = state.get(key)
    assert isinstance(value, str)
    return value


def _require_list(state: AnalyticsGraphState, key: str) -> list[str]:
    value = state.get(key)
    assert isinstance(value, list)
    return cast(list[str], value)


def _require_router_decision(state: AnalyticsGraphState) -> RouterDecision:
    value = state.get("router_decision")
    assert value is not None
    return RouterDecision.model_validate(value)


def test_graph_executes_traffic_volume_tool_and_synthesizes_answer(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    question = "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"

    state = invoke_analytics_graph(
        question,
        graph=graph_bundle.graph,
        thread_id="traffic-volume-thread",
    )

    assert _require_list(state, "tools_used") == ["traffic_volume_analyzer"]
    assert _require_str(state, "final_answer") == (
        f"SYNTH::traffic_volume_analyzer::{question}"
    )
    assert len(graph_bundle.tools.calls) == 1
    assert graph_bundle.tools.calls[0].tool_name == "traffic_volume_analyzer"
    assert graph_bundle.llm.prompts


def test_graph_short_circuits_missing_dates_without_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    state = invoke_analytics_graph(
        "Qual foi a receita de Search?",
        graph=graph_bundle.graph,
        thread_id="missing-dates-thread",
    )

    assert _require_str(state, "final_answer") == MISSING_DATES_MESSAGE
    assert _require_list(state, "tools_used") == []
    assert graph_bundle.tools.calls == []


def test_graph_merges_date_follow_up_from_same_thread(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "clarification-thread"
    first_question = "Qual foi a receita de Search?"
    second_question = "Entre 2024-01-01 e 2024-01-31."

    first_state = invoke_analytics_graph(
        first_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        second_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert _require_str(first_state, "final_answer") == MISSING_DATES_MESSAGE
    assert _require_list(second_state, "tools_used") == ["channel_performance_analyzer"]
    assert (
        _require_str(second_state, "resolved_question")
        == "Qual foi a receita de Search? Entre 2024-01-01 e 2024-01-31."
    )
    assert router_decision.normalized_params.traffic_source == "Search"
    assert len(graph_bundle.tools.calls) == 1
    assert graph_bundle.tools.calls[0].tool_name == "channel_performance_analyzer"
    assert graph_bundle.tools.calls[0].traffic_source == "Search"


def test_graph_routes_strategy_follow_up_without_new_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "strategy-thread"
    analysis_question = (
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"
    )
    follow_up_question = "Quais acoes devemos priorizar para reduzir essa dependencia dos canais?"

    first_state = invoke_analytics_graph(
        analysis_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        follow_up_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert _require_list(first_state, "tools_used") == ["channel_performance_analyzer"]
    assert len(graph_bundle.tools.calls) == 1
    assert _require_list(second_state, "tools_used") == []
    assert _require_str(second_state, "final_answer") == (
        f"FOLLOW_UP::{follow_up_question}"
    )
    assert router_decision.intent == "strategy_follow_up"
    assert len(graph_bundle.tools.calls) == 1


def test_graph_routes_diagnostic_follow_up_without_new_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "diagnostic-thread"
    analysis_question = (
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"
    )
    follow_up_question = "O que explica essa concentracao de receita?"

    invoke_analytics_graph(
        analysis_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        follow_up_question,
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert _require_list(second_state, "tools_used") == []
    assert _require_str(second_state, "final_answer") == (
        f"FOLLOW_UP::{follow_up_question}"
    )
    assert router_decision.intent == "diagnostic_follow_up"
    assert len(graph_bundle.tools.calls) == 1


def test_graph_treats_follow_up_with_new_channel_as_new_question(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "source-change-thread"

    invoke_analytics_graph(
        "Como o Search performou ontem?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "receita de Facebook",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert _require_str(second_state, "final_answer") == MISSING_DATES_MESSAGE
    assert _require_list(second_state, "tools_used") == []
    assert _require_str(second_state, "resolved_question") == "receita de Facebook"
    assert router_decision.normalized_params.traffic_source == "Facebook"
    assert graph_bundle.tools.calls == []


def test_graph_resets_final_answer_between_short_circuits(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "short-circuit-thread"
    first_state = invoke_analytics_graph(
        "Qual foi a receita de Search?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "Qual foi a receita por campanha entre 2024-01-01 e 2024-01-31?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )

    first_answer = _require_str(first_state, "final_answer")
    second_answer = _require_str(second_state, "final_answer")

    assert first_answer == MISSING_DATES_MESSAGE
    assert second_answer == UNSUPPORTED_DIMENSION_MESSAGE
    assert second_answer != first_answer
    assert _require_list(second_state, "tools_used") == []
