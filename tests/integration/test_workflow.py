from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph.workflow import (
    AnalyticsGraphState,
    MISSING_DATES_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    build_analytics_graph,
    invoke_analytics_graph,
)
from app.schemas.router import RouterDecision
from tests.fakes import (
    DeterministicGraphBundle,
    FakeAgentLLM,
    FakeAnalyticsTools,
    FakeSynthesisLLM,
    build_deterministic_graph_bundle,
)


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


def test_graph_llm_decides_to_call_traffic_volume_tool(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    """The LLM (via FakeAgentLLM) should emit tool_calls, which ToolNode executes,
    and then the LLM synthesizes a final answer — the full tool calling cycle."""
    question = "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"

    state = invoke_analytics_graph(
        question,
        graph=graph_bundle.graph,
        thread_id="traffic-volume-thread",
    )

    final_answer = _require_str(state, "final_answer")
    tools_used = _require_list(state, "tools_used")

    # The LLM decided to call traffic_volume_analyzer.
    assert "traffic_volume_analyzer" in tools_used
    # The agent synthesized an answer after receiving the tool result.
    assert final_answer.startswith("SYNTH::traffic_volume_analyzer::")
    # The tool was actually executed via ToolNode.
    assert len(graph_bundle.tools.calls) == 1
    assert graph_bundle.tools.calls[0].tool_name == "traffic_volume_analyzer"
    # The agent LLM was invoked (first for tool_calls, then for synthesis).
    assert len(graph_bundle.agent_llm.prompts) >= 1


def test_graph_routes_aggregate_user_volume_query_without_channel(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    question = "Usuarios nos ultimos 7 dias"

    state = invoke_analytics_graph(
        question,
        graph=graph_bundle.graph,
        thread_id="aggregate-traffic-volume-thread",
    )
    router_decision = _require_router_decision(state)

    assert "traffic_volume_analyzer" in _require_list(state, "tools_used")
    assert _require_str(state, "final_answer").startswith("SYNTH::traffic_volume_analyzer::")
    assert router_decision.intent == "traffic_volume"
    assert router_decision.refusal_reason is None
    assert router_decision.normalized_params.traffic_source is None
    assert router_decision.normalized_params.start_date is not None
    assert router_decision.normalized_params.end_date is not None
    assert (
        router_decision.normalized_params.end_date
        - router_decision.normalized_params.start_date
    ).days == 6
    assert len(graph_bundle.tools.calls) == 1
    assert graph_bundle.tools.calls[0].tool_name == "traffic_volume_analyzer"
    assert graph_bundle.tools.calls[0].traffic_source is None


def test_graph_llm_decides_to_call_channel_performance_tool(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    """The LLM should select channel_performance_analyzer for revenue questions."""
    question = "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"

    state = invoke_analytics_graph(
        question,
        graph=graph_bundle.graph,
        thread_id="channel-perf-thread",
    )

    tools_used = _require_list(state, "tools_used")
    final_answer = _require_str(state, "final_answer")

    assert "channel_performance_analyzer" in tools_used
    assert final_answer.startswith("SYNTH::channel_performance_analyzer::")
    assert len(graph_bundle.tools.calls) == 1
    assert graph_bundle.tools.calls[0].tool_name == "channel_performance_analyzer"


def test_graph_short_circuits_missing_dates_without_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    """Short-circuits bypass the LLM agent entirely — no tool calls, no LLM tokens."""
    state = invoke_analytics_graph(
        "Qual foi a receita de Search?",
        graph=graph_bundle.graph,
        thread_id="missing-dates-thread",
    )

    assert _require_str(state, "final_answer") == MISSING_DATES_MESSAGE
    assert _require_list(state, "tools_used") == []
    assert graph_bundle.tools.calls == []
    # The agent LLM should NOT have been called for a short-circuit.
    assert len(graph_bundle.agent_llm.prompts) == 0


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
    assert "channel_performance_analyzer" in _require_list(second_state, "tools_used")
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

    assert "channel_performance_analyzer" in _require_list(first_state, "tools_used")
    # Follow-up uses insight_synthesizer (FakeSynthesisLLM), not the agent.
    assert len(graph_bundle.tools.calls) == 1
    assert _require_list(second_state, "tools_used") == []
    assert _require_str(second_state, "final_answer") == (
        f"FOLLOW_UP::{follow_up_question}"
    )
    assert router_decision.intent == "strategy_follow_up"
    assert len(graph_bundle.tools.calls) == 1


def test_graph_routes_anaphoric_strategy_follow_up_without_new_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "anaphoric-strategy-thread"
    analysis_question = (
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"
    )
    follow_up_question = "Monte essa analise e me retorne"

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


def test_graph_routes_multichannel_diagnostic_follow_up_without_new_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "multichannel-diagnostic-thread"
    analysis_question = (
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"
    )
    follow_up_question = "Por que Organic ficou abaixo de Search?"

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


def test_graph_routes_contextual_comparison_follow_up_without_new_tool_execution(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "comparison-follow-up-thread"
    analysis_question = (
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?"
    )
    follow_up_question = (
        "Responda se o canal esta performando melhor ou pior do que os outros"
    )

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
    assert router_decision.refusal_reason is None
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


def test_graph_treats_explicit_channel_query_after_aggregate_analysis_as_new_question(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "aggregate-source-change-thread"

    invoke_analytics_graph(
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?",
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
    assert router_decision.intent == "channel_performance"
    assert router_decision.normalized_params.traffic_source == "Facebook"
    assert len(graph_bundle.tools.calls) == 1


def test_graph_infers_generic_follow_up_intent_from_previous_diagnostic_turn(
    graph_bundle: DeterministicGraphBundle,
) -> None:
    thread_id = "generic-diagnostic-thread"

    invoke_analytics_graph(
        "Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    invoke_analytics_graph(
        "O que explica essa concentracao de receita?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    third_state = invoke_analytics_graph(
        "me ajude entao",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(third_state)

    assert _require_list(third_state, "tools_used") == []
    assert _require_str(third_state, "final_answer") == "FOLLOW_UP::me ajude entao"
    assert router_decision.intent == "diagnostic_follow_up"


@dataclass
class ClarifyingAgentLLM(FakeAgentLLM):
    prompts: list[str] = field(default_factory=list)

    def invoke(self, messages: list[object]) -> AIMessage:
        last_content = ""
        if messages:
            last_message = messages[-1]
            last_content = getattr(last_message, "content", "")
            if not isinstance(last_content, str):
                last_content = str(last_content)
        self.prompts.append(last_content)

        if self._has_tool_message(messages):
            tool_name = "unknown"
            question = ""
            from langchain_core.messages import HumanMessage

            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and msg.name:
                    tool_name = msg.name
                    break

            for msg in messages:
                if isinstance(msg, HumanMessage):
                    question = str(msg.content)
                    break

            return AIMessage(content=f"SYNTH::{tool_name}::{question}")

        from langchain_core.messages import HumanMessage

        all_human_text = " ".join(
            str(msg.content)
            for msg in messages
            if isinstance(msg, HumanMessage)
        ).lower()
        if (
            "volume de trafego este mes" in all_human_text
            and "total" not in all_human_text
            and "compar" not in all_human_text
            and "canal" not in all_human_text
        ):
            return AIMessage(
                content=(
                    "Claro — para eu trazer o volume de trafego deste mes, preciso "
                    "de uma coisa antes: voce quer o volume total ou comparar por canal "
                    "(ex.: Search, Organic, Facebook)?"
                )
            )

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "traffic_volume_analyzer",
                    "args": {
                        "start_date": "2026-04-01",
                        "end_date": "2026-04-21",
                        "traffic_source": None,
                    },
                    "id": str(uuid4()),
                    "type": "tool_call",
                }
            ],
        )


@dataclass
class ParaphrasedAmbiguousMetricClarifyingAgentLLM(FakeAgentLLM):
    prompts: list[str] = field(default_factory=list)

    def invoke(self, messages: list[object]) -> AIMessage:
        last_content = ""
        if messages:
            last_message = messages[-1]
            last_content = getattr(last_message, "content", "")
            if not isinstance(last_content, str):
                last_content = str(last_content)
        self.prompts.append(last_content)

        from langchain_core.messages import HumanMessage

        all_human_text = " ".join(
            str(msg.content)
            for msg in messages
            if isinstance(msg, HumanMessage)
        ).lower()
        if (
            "performou ontem" in all_human_text
            and "volume" not in all_human_text
            and "usuario" not in all_human_text
            and "receita" not in all_human_text
            and "pedido" not in all_human_text
        ):
            return AIMessage(content="Voce quer olhar usuarios ou receita/pedidos?")

        return super().invoke(messages)


def test_graph_merges_short_reply_after_agent_opened_clarification() -> None:
    clarifying_agent_llm = ClarifyingAgentLLM()
    synthesis_llm = FakeSynthesisLLM()
    fake_tools = FakeAnalyticsTools()
    graph = build_analytics_graph(
        agent_llm=clarifying_agent_llm,
        response_llm=synthesis_llm,
        tools=fake_tools.build(),
        checkpointer=MemorySaver(),
    )

    thread_id = "agent-clarification-thread"
    first_state = invoke_analytics_graph(
        "volume de trafego este mes",
        graph=graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "total",
        graph=graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert (
        _require_str(first_state, "final_answer")
        == "Claro — para eu trazer o volume de trafego deste mes, preciso de uma coisa antes: voce quer o volume total ou comparar por canal (ex.: Search, Organic, Facebook)?"
    )
    assert "traffic_volume_analyzer" in _require_list(second_state, "tools_used")
    assert _require_str(second_state, "resolved_question") == "volume de trafego este mes total"
    assert router_decision.intent == "traffic_volume"
    assert router_decision.refusal_reason is None


<<<<<<< Updated upstream
=======
def test_graph_merges_metric_choice_after_agent_opened_ambiguous_analytics_clarification() -> None:
    graph_bundle = build_deterministic_graph_bundle()
    thread_id = "ambiguous-analytics-clarification-thread"

    first_state = invoke_analytics_graph(
        "Como o Search performou ontem?",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "volume de usuarios",
        graph=graph_bundle.graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert "volume de usuarios ou performance financeira" in _require_str(
        first_state, "final_answer"
    )
    assert "traffic_volume_analyzer" in _require_list(second_state, "tools_used")
    assert (
        _require_str(second_state, "resolved_question")
        == "Como o Search performou ontem? volume de usuarios"
    )
    assert router_decision.intent == "traffic_volume"
    assert router_decision.normalized_params.traffic_source == "Search"
    assert router_decision.normalized_params.start_date is not None
    assert router_decision.normalized_params.end_date is not None


def test_graph_merges_metric_choice_after_paraphrased_agent_clarification() -> None:
    clarifying_agent_llm = ParaphrasedAmbiguousMetricClarifyingAgentLLM()
    synthesis_llm = FakeSynthesisLLM()
    fake_tools = FakeAnalyticsTools()
    graph = build_analytics_graph(
        agent_llm=clarifying_agent_llm,
        response_llm=synthesis_llm,
        tools=fake_tools.build(),
        checkpointer=MemorySaver(),
    )

    thread_id = "paraphrased-ambiguous-analytics-clarification-thread"
    first_state = invoke_analytics_graph(
        "Como o Search performou ontem?",
        graph=graph,
        thread_id=thread_id,
    )
    second_state = invoke_analytics_graph(
        "receita",
        graph=graph,
        thread_id=thread_id,
    )
    router_decision = _require_router_decision(second_state)

    assert _require_str(first_state, "final_answer") == (
        "Voce quer olhar usuarios ou receita/pedidos?"
    )
    assert "channel_performance_analyzer" in _require_list(second_state, "tools_used")
    assert _require_str(second_state, "resolved_question") == (
        "Como o Search performou ontem? receita"
    )
    assert router_decision.intent == "channel_performance"
    assert router_decision.normalized_params.traffic_source == "Search"
    assert router_decision.normalized_params.start_date is not None
    assert router_decision.normalized_params.end_date is not None


>>>>>>> Stashed changes
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
