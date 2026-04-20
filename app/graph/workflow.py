from __future__ import annotations

from functools import lru_cache
import json
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from app.graph.llm import (
    LlmTimeoutError,
    build_analytics_llm,
    is_llm_timeout_error,
)
from app.graph.prompts import FINAL_RESPONSE_SYSTEM_PROMPT
from app.graph.router import (
    EMPTY_QUESTION_MESSAGE,
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    build_router_decision,
    question_introduces_new_traffic_source,
    question_is_metric_clarification_follow_up,
    question_contains_temporal_signal,
    strip_temporal_context,
)
from app.schemas.router import RouterDecision
from app.graph.tools import get_analytics_tools
from app.utils.config import Settings, get_settings
TEMPORARY_LLM_FAILURE_MESSAGE = (
    "Nao consegui concluir a analise agora por uma falha temporaria. Tente novamente em instantes."
)
TEMPORARY_TOOL_FAILURE_MESSAGE = (
    "Nao consegui consultar os dados agora por uma falha temporaria. Tente novamente em instantes."
)


class AnalyticsGraphState(TypedDict, total=False):
    question: str
    messages: Annotated[list[AnyMessage], add_messages]
    router_decision: dict[str, Any]
    resolved_question: str
    turn_start_index: int
    final_answer: str
    tools_used: list[str]
    debug_errors: list[dict[str, Any]]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
                    continue
                parts.append(json.dumps(item, ensure_ascii=False, default=str))
                continue
            parts.append(str(item))
        return "\n".join(parts)

    return str(content)


def _stringify_exception(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or repr(exc)


def _build_debug_error(
    source: str,
    *,
    message: str,
    error_type: str | None = None,
    tool_name: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "message": message,
        "error_type": error_type,
        "tool_name": tool_name,
    }


def _resolve_question(state: AnalyticsGraphState) -> str:
    question = state.get("question", "").strip()
    if question:
        return question

    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            content = _content_to_text(message.content).strip()
            if content:
                return content

    return ""


def _resolve_effective_question(state: AnalyticsGraphState) -> str:
    resolved_question = state.get("resolved_question", "").strip()
    if resolved_question:
        return resolved_question
    return _resolve_question(state)


def _collect_tool_messages(messages: list[AnyMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


def _get_last_human_question(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            question = _content_to_text(message.content).strip()
            if question:
                return question
    return ""


def _resolve_turn_start_index(state: AnalyticsGraphState) -> int:
    messages = list(state.get("messages", []))
    explicit_question = state.get("question", "").strip()

    if explicit_question:
        if messages and isinstance(messages[-1], HumanMessage):
            last_human_content = _content_to_text(messages[-1].content).strip()
            if last_human_content == explicit_question:
                return len(messages) - 1
        return len(messages)

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index

    return len(messages)


def _get_current_turn_messages(state: AnalyticsGraphState) -> list[AnyMessage]:
    messages = list(state.get("messages", []))
    turn_start_index = state.get("turn_start_index", _resolve_turn_start_index(state))
    bounded_start_index = max(0, min(turn_start_index, len(messages)))
    return messages[bounded_start_index:]


def _build_turn_question_messages(state: AnalyticsGraphState) -> list[HumanMessage]:
    question = _resolve_question(state)
    if not question:
        return []

    explicit_question = state.get("question", "").strip()
    existing_messages = list(state.get("messages", []))
    last_message = existing_messages[-1] if existing_messages else None

    if explicit_question:
        if isinstance(last_message, HumanMessage):
            last_human_content = _content_to_text(last_message.content).strip()
            if last_human_content == explicit_question:
                return []
        return [HumanMessage(content=explicit_question)]

    if not existing_messages:
        return [HumanMessage(content=question)]

    return []


def _collect_tools_used(messages: list[AnyMessage]) -> list[str]:
    seen: set[str] = set()
    tools_used: list[str] = []

    for message in messages:
        if not isinstance(message, ToolMessage) or not message.name:
            continue
        if message.name in seen:
            continue
        seen.add(message.name)
        tools_used.append(message.name)

    return tools_used


def _serialize_tool_result(result: Any) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def _build_temporary_failure_ai_message() -> AIMessage:
    return AIMessage(content=TEMPORARY_LLM_FAILURE_MESSAGE)


def _serialize_router_decision(router_decision: RouterDecision) -> dict[str, Any]:
    return router_decision.model_dump(mode="json")


def _deserialize_router_decision(
    router_decision: dict[str, Any] | RouterDecision | None,
) -> RouterDecision | None:
    if router_decision is None:
        return None
    if isinstance(router_decision, RouterDecision):
        return router_decision
    return RouterDecision.model_validate(router_decision)


def _router_decision_short_circuits(router_decision: RouterDecision) -> bool:
    return (
        router_decision.needs_clarification
        or router_decision.refusal_reason is not None
    )


def _resolve_expected_tool_name(router_decision: RouterDecision | None) -> str | None:
    if router_decision is None:
        return None
    if router_decision.intent == "traffic_volume":
        return "traffic_volume_analyzer"
    if router_decision.intent == "channel_performance":
        return "channel_performance_analyzer"
    return None


def _build_router_tool_args(router_decision: RouterDecision) -> dict[str, Any]:
    normalized_params = router_decision.normalized_params
    return {
        "traffic_source": normalized_params.traffic_source,
        "start_date": (
            normalized_params.start_date.isoformat()
            if normalized_params.start_date is not None
            else None
        ),
        "end_date": (
            normalized_params.end_date.isoformat()
            if normalized_params.end_date is not None
            else None
        ),
    }


def _resolve_router_turn(
    state: AnalyticsGraphState,
    question: str,
) -> tuple[str, RouterDecision]:
    router_decision = build_router_decision(question)
    previous_router_decision = _deserialize_router_decision(state.get("router_decision"))
    follow_up_changes_traffic_source = (
        previous_router_decision is not None
        and question_introduces_new_traffic_source(
            question,
            previous_traffic_source=(
                previous_router_decision.normalized_params.traffic_source
            ),
        )
    )

    should_merge_temporal_follow_up = (
        previous_router_decision is not None
        and previous_router_decision.needs_clarification
        and previous_router_decision.clarification_reason in {"missing_dates", "invalid_dates"}
        and question_contains_temporal_signal(question)
        and not follow_up_changes_traffic_source
        and (
            (
                previous_router_decision.clarification_reason == "invalid_dates"
                and previous_router_decision.intent == "ambiguous_analytics"
            )
            or
            router_decision.intent in {"out_of_scope", "ambiguous_analytics"}
            or router_decision.intent == previous_router_decision.intent
        )
    )
    should_merge_metric_follow_up = (
        previous_router_decision is not None
        and previous_router_decision.needs_clarification
        and previous_router_decision.clarification_reason == "ambiguous_metric"
        and question_is_metric_clarification_follow_up(question)
        and not follow_up_changes_traffic_source
    )

    if (
        not should_merge_temporal_follow_up
        and not should_merge_metric_follow_up
    ):
        return question, router_decision

    previous_question = _get_last_human_question(list(state.get("messages", [])))
    if not previous_question:
        return question, router_decision

    previous_question_for_merge = previous_question
    if previous_router_decision is not None:
        if previous_router_decision.clarification_reason == "invalid_dates":
            previous_question_for_merge = strip_temporal_context(previous_question)

    merged_question = (
        f"{previous_question_for_merge.rstrip()} {question.strip()}".strip()
    )
    merged_router_decision = build_router_decision(merged_question)
    if (
        merged_router_decision.intent == "out_of_scope"
        and not merged_router_decision.needs_clarification
    ):
        return question, router_decision

    return merged_question, merged_router_decision


def build_analytics_graph(
    settings: Settings | None = None,
    *,
    response_llm: Any | None = None,
    tools: tuple[BaseTool, ...] | None = None,
    checkpointer: BaseCheckpointSaver | bool | None = None,
) -> Any:
    analytics_tools = tools or get_analytics_tools()
    tools_by_name = {tool.name: tool for tool in analytics_tools}
    synthesis_llm = response_llm or build_analytics_llm(settings)

    def router_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["tool_executor", "insight_synthesizer"]]:
        question = _resolve_question(state)
        turn_start_index = _resolve_turn_start_index(state)
        injected_messages = _build_turn_question_messages(state)
        resolved_question, router_decision = _resolve_router_turn(state, question)
        serialized_router_decision = _serialize_router_decision(router_decision)
        state_update: dict[str, Any] = {
            "router_decision": serialized_router_decision,
            "resolved_question": resolved_question,
            "turn_start_index": turn_start_index,
            "debug_errors": [],
        }

        if injected_messages:
            state_update["messages"] = injected_messages

        if _router_decision_short_circuits(router_decision):
            state_update["final_answer"] = (
                router_decision.response_message or EMPTY_QUESTION_MESSAGE
            )
            return Command(update=state_update, goto="insight_synthesizer")

        return Command(update=state_update, goto="tool_executor")

    def tool_executor_node(state: AnalyticsGraphState) -> dict[str, Any]:
        router_decision = _deserialize_router_decision(state.get("router_decision"))

        tool_messages: list[ToolMessage] = []
        expected_tool_name = _resolve_expected_tool_name(router_decision)

        if router_decision is None or expected_tool_name is None:
            return {
                "messages": [
                    ToolMessage(
                        tool_call_id="router-decision-missing",
                        name="unknown",
                        status="error",
                        content=(
                            "Nao foi possivel resolver uma tool a partir da decisao "
                            "estruturada do roteador."
                        ),
                    )
                ],
                "debug_errors": [
                    _build_debug_error(
                        "tool_executor",
                        message=(
                            "Nao foi possivel mapear a decisao do roteador para uma "
                            "tool executavel."
                        ),
                    )
                ],
            }

        resolved_tool_args = _build_router_tool_args(router_decision)
        tool = tools_by_name.get(expected_tool_name)

        if tool is None:
            return {
                "messages": [
                    ToolMessage(
                        tool_call_id=expected_tool_name,
                        name=expected_tool_name,
                        status="error",
                        content=(
                            "A tool esperada pela decisao do roteador nao esta "
                            f"registrada: {expected_tool_name}."
                        ),
                    )
                ],
                "debug_errors": [
                    _build_debug_error(
                        "tool_executor",
                        message=(
                            "A tool esperada pela decisao do roteador nao esta registrada."
                        ),
                        tool_name=expected_tool_name,
                    )
                ],
            }

        try:
            result = tool.invoke(resolved_tool_args)
            tool_messages.append(
                ToolMessage(
                    tool_call_id=expected_tool_name,
                    name=expected_tool_name,
                    content=_serialize_tool_result(result),
                    artifact=result,
                )
            )
        except Exception as exc:
            tool_messages.append(
                ToolMessage(
                    tool_call_id=expected_tool_name,
                    name=expected_tool_name,
                    status="error",
                    content=(
                        f"Falha temporaria ao executar {expected_tool_name}: "
                        f"{_stringify_exception(exc)}"
                    ),
                )
            )
            return {
                "messages": tool_messages,
                "debug_errors": [
                    _build_debug_error(
                        "tool_executor",
                        message=_stringify_exception(exc),
                        error_type=type(exc).__name__,
                        tool_name=expected_tool_name,
                    )
                ],
            }

        return {"messages": tool_messages}

    def insight_synthesizer_node(state: AnalyticsGraphState) -> dict[str, Any]:
        current_turn_messages = _get_current_turn_messages(state)
        tools_used = _collect_tools_used(current_turn_messages)
        preset_answer = state.get("final_answer")
        tool_messages = _collect_tool_messages(current_turn_messages)

        if preset_answer and not tool_messages:
            return {
                "final_answer": preset_answer,
                "tools_used": tools_used,
            }

        if any(message.status == "error" for message in tool_messages):
            return {
                "final_answer": TEMPORARY_TOOL_FAILURE_MESSAGE,
                "tools_used": tools_used,
            }

        if tool_messages:
            question = _resolve_effective_question(state)
            tool_context = "\n\n".join(
                f"Tool: {message.name}\nResultado:\n{_content_to_text(message.content)}"
                for message in tool_messages
            )
            try:
                synthesized_response = cast(
                    AIMessage,
                    synthesis_llm.invoke(
                        [
                            SystemMessage(content=FINAL_RESPONSE_SYSTEM_PROMPT),
                            HumanMessage(
                                content=(
                                    f"Pergunta original:\n{question}\n\n"
                                    f"Resultados estruturados:\n{tool_context}"
                                )
                            ),
                        ]
                    ),
                )
            except Exception as exc:
                if is_llm_timeout_error(exc):
                    raise LlmTimeoutError(
                        "Tempo limite excedido ao sintetizar a resposta final.",
                        source="insight_synthesizer",
                        error_type=type(exc).__name__,
                        debug_message=_stringify_exception(exc),
                    ) from exc
                return {
                    "messages": [_build_temporary_failure_ai_message()],
                    "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
                    "tools_used": tools_used,
                    "debug_errors": [
                        _build_debug_error(
                            "insight_synthesizer",
                            message=_stringify_exception(exc),
                            error_type=type(exc).__name__,
                        )
                    ],
                }
            return {
                "messages": [synthesized_response],
                "final_answer": _content_to_text(synthesized_response.content).strip(),
                "tools_used": tools_used,
            }

        return {
            "final_answer": TEMPORARY_TOOL_FAILURE_MESSAGE,
            "tools_used": tools_used,
        }

    graph = StateGraph(AnalyticsGraphState)
    graph.add_node("router", router_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("insight_synthesizer", insight_synthesizer_node)

    graph.add_edge(START, "router")
    graph.add_edge("tool_executor", "insight_synthesizer")
    graph.add_edge("insight_synthesizer", END)

    return graph.compile(checkpointer=checkpointer)


@lru_cache
def get_persistent_analytics_graph() -> Any:
    """Return a cached graph compiled with in-memory checkpoint persistence."""

    return build_analytics_graph(get_settings(), checkpointer=MemorySaver())


def invoke_analytics_graph(
    question: str,
    settings: Settings | None = None,
    *,
    thread_id: str | None = None,
    graph: Any | None = None,
) -> AnalyticsGraphState:
    resolved_graph = graph
    if resolved_graph is None:
        resolved_graph = (
            get_persistent_analytics_graph()
            if thread_id
            else build_analytics_graph(settings)
        )

    config: dict[str, Any] | None = None
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}

    input_state: AnalyticsGraphState = {
        "question": question,
        # Reset overwrite-style per-turn fields so resumed checkpoints do not
        # leak the previous turn's answer or tool list into the current turn.
        "final_answer": "",
        "tools_used": [],
    }

    return cast(AnalyticsGraphState, resolved_graph.invoke(input_state, config=config))


__all__ = [
    "AnalyticsGraphState",
    "INVALID_DATES_MESSAGE",
    "MISSING_DATES_MESSAGE",
    "OUT_OF_SCOPE_MESSAGE",
    "TEMPORARY_LLM_FAILURE_MESSAGE",
    "TEMPORARY_TOOL_FAILURE_MESSAGE",
    "UNSUPPORTED_DIMENSION_MESSAGE",
    "build_analytics_graph",
    "get_persistent_analytics_graph",
    "invoke_analytics_graph",
]
