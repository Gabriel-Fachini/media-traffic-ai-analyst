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
    build_tool_enabled_llm,
    is_llm_timeout_error,
)
from app.graph.prompts import (
    DIAGNOSTIC_FOLLOW_UP_SYSTEM_PROMPT,
    STRATEGY_FOLLOW_UP_SYSTEM_PROMPT,
    build_conversation_system_prompt,
)
from app.graph.router import (
    EMPTY_QUESTION_MESSAGE,
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    build_router_decision,
    question_introduces_new_traffic_source,
    question_is_diagnostic_follow_up,
    question_is_metric_clarification_follow_up,
    question_is_strategy_follow_up,
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

# Safety guard: max agent/tool iterations per turn to prevent infinite loops.
_MAX_AGENT_ITERATIONS = 3


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


def _is_successful_tool_message(message: AnyMessage) -> bool:
    return isinstance(message, ToolMessage) and message.status != "error"


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


def _has_prior_successful_tool_context(state: AnalyticsGraphState) -> bool:
    messages = list(state.get("messages", []))
    turn_start_index = _resolve_turn_start_index(state)
    bounded_turn_start_index = max(0, min(turn_start_index, len(messages)))
    return any(
        _is_successful_tool_message(message)
        for message in messages[:bounded_turn_start_index]
    )


def _build_strategy_follow_up_context(state: AnalyticsGraphState) -> str | None:
    messages = list(state.get("messages", []))
    turn_start_index = state.get("turn_start_index", _resolve_turn_start_index(state))
    bounded_turn_start_index = max(0, min(turn_start_index, len(messages)))
    previous_messages = messages[:bounded_turn_start_index]

    last_tool_index: int | None = None
    for index in range(len(previous_messages) - 1, -1, -1):
        if _is_successful_tool_message(previous_messages[index]):
            last_tool_index = index
            break

    if last_tool_index is None:
        return None

    previous_turn_start_index = 0
    for index in range(last_tool_index, -1, -1):
        if isinstance(previous_messages[index], HumanMessage):
            previous_turn_start_index = index
            break

    previous_turn_messages = previous_messages[previous_turn_start_index:]
    previous_question = ""
    if (
        previous_turn_messages
        and isinstance(previous_turn_messages[0], HumanMessage)
    ):
        previous_question = _content_to_text(previous_turn_messages[0].content).strip()

    previous_answer = ""
    for message in reversed(previous_turn_messages):
        if not isinstance(message, AIMessage):
            continue
        previous_answer = _content_to_text(message.content).strip()
        if previous_answer:
            break

    tool_context_blocks = [
        f"Tool: {message.name}\nResultado:\n{_content_to_text(message.content)}"
        for message in previous_turn_messages
        if _is_successful_tool_message(message)
    ]

    if not previous_question and not previous_answer and not tool_context_blocks:
        return None

    context_blocks: list[str] = []
    if previous_question:
        context_blocks.append(f"Pergunta anterior:\n{previous_question}")
    if previous_answer:
        context_blocks.append(f"Resposta anterior:\n{previous_answer}")
    if tool_context_blocks:
        context_blocks.append(
            "Resultados anteriores de tools:\n" + "\n\n".join(tool_context_blocks)
        )
    return "\n\n".join(context_blocks)


def _resolve_follow_up_intent(
    question: str,
    *,
    has_prior_context: bool,
) -> Literal["strategy_follow_up", "diagnostic_follow_up"] | None:
    if not has_prior_context:
        return None

    if question_is_strategy_follow_up(question):
        return "strategy_follow_up"

    if question_is_diagnostic_follow_up(question):
        return "diagnostic_follow_up"

    return None


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
    follow_up_intent = _resolve_follow_up_intent(
        question,
        has_prior_context=_has_prior_successful_tool_context(state),
    )
    if (
        (
            router_decision.refusal_reason in {"out_of_scope", "unsupported_dimension"}
            or (
                router_decision.needs_clarification
                and router_decision.clarification_reason == "missing_dates"
            )
        )
        and not follow_up_changes_traffic_source
        and follow_up_intent is not None
    ):
        return (
            question,
            RouterDecision(
                intent=follow_up_intent,
                normalized_params=router_decision.normalized_params,
            ),
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


def _count_agent_iterations_in_turn(state: AnalyticsGraphState) -> int:
    """Count how many times the agent node has run in the current turn."""
    current_turn_messages = _get_current_turn_messages(state)
    return sum(
        1 for msg in current_turn_messages
        if isinstance(msg, AIMessage) and msg.tool_calls
    )


def build_analytics_graph(
    settings: Settings | None = None,
    *,
    agent_llm: Any | None = None,
    response_llm: Any | None = None,
    tools: tuple[BaseTool, ...] | None = None,
    checkpointer: BaseCheckpointSaver | bool | None = None,
) -> Any:
    analytics_tools = tools or get_analytics_tools()
    # agent_llm: LLM with tools bound — drives tool calling decisions.
    # response_llm: plain LLM (no tools) — used only for follow-up synthesis.
    resolved_agent_llm = agent_llm or build_tool_enabled_llm(settings)
    resolved_response_llm = response_llm or build_analytics_llm(settings)
    tools_by_name: dict[str, BaseTool] = {tool.name: tool for tool in analytics_tools}
    agent_system_prompt = build_conversation_system_prompt()

    def router_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["agent", "scope_guard", "insight_synthesizer"]]:
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

        # Follow-ups (strategy/diagnostic) go straight to synthesis, no new tool calls.
        if router_decision.intent in {
            "strategy_follow_up",
            "diagnostic_follow_up",
        }:
            return Command(update=state_update, goto="insight_synthesizer")

        # Short-circuits (refusal, clarification) bypass LLM entirely.
        if _router_decision_short_circuits(router_decision):
            state_update["final_answer"] = (
                router_decision.response_message or EMPTY_QUESTION_MESSAGE
            )
            return Command(update=state_update, goto="scope_guard")

        # Analytics intents (traffic_volume, channel_performance) go to the LLM agent.
        return Command(update=state_update, goto="agent")

    def agent_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["tool_executor", "__end__"]]:
        """LLM agent that decides which tool to call, then synthesizes the final answer."""
        # Safety guard: prevent runaway loops.
        iterations = _count_agent_iterations_in_turn(state)
        if iterations >= _MAX_AGENT_ITERATIONS:
            current_turn_messages = _get_current_turn_messages(state)
            tools_used = _collect_tools_used(current_turn_messages)
            return Command(
                update={
                    "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
                    "tools_used": tools_used,
                    "debug_errors": [
                        _build_debug_error(
                            "agent",
                            message=(
                                f"Limite de {_MAX_AGENT_ITERATIONS} iteracoes atingido "
                                "no loop agent/tool."
                            ),
                        )
                    ],
                },
                goto="__end__",
            )

        # Build the messages for this agent invocation: system + current turn history.
        # Always use the resolved_question (which may be a merged clarification) as the
        # first HumanMessage so the LLM receives the full canonical context, not just
        # the raw last user input.
        current_turn_messages = _get_current_turn_messages(state)
        resolved_question = _resolve_effective_question(state)
        if resolved_question:
            # Replace or prepend the first HumanMessage with the resolved question.
            non_human_prefix: list[AnyMessage] = []
            rest_of_turn: list[AnyMessage] = list(current_turn_messages)
            if rest_of_turn and isinstance(rest_of_turn[0], HumanMessage):
                rest_of_turn = rest_of_turn[1:]
            agent_turn_messages: list[AnyMessage] = (
                [HumanMessage(content=resolved_question)] + non_human_prefix + rest_of_turn
            )
        else:
            agent_turn_messages = list(current_turn_messages)

        llm_input = [SystemMessage(content=agent_system_prompt)] + agent_turn_messages

        try:
            response = cast(AIMessage, resolved_agent_llm.invoke(llm_input))
        except Exception as exc:
            if is_llm_timeout_error(exc):
                raise LlmTimeoutError(
                    "Tempo limite excedido no nó agente.",
                    source="agent",
                    error_type=type(exc).__name__,
                    debug_message=_stringify_exception(exc),
                ) from exc
            current_turn_messages_for_error = _get_current_turn_messages(state)
            tools_used = _collect_tools_used(current_turn_messages_for_error)
            return Command(
                update={
                    "messages": [_build_temporary_failure_ai_message()],
                    "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
                    "tools_used": tools_used,
                    "debug_errors": [
                        _build_debug_error(
                            "agent",
                            message=_stringify_exception(exc),
                            error_type=type(exc).__name__,
                        )
                    ],
                },
                goto="__end__",
            )

        # If the LLM decided to call tools, store the AIMessage and route to executor.
        if response.tool_calls:
            return Command(
                update={"messages": [response]},
                goto="tool_executor",
            )

        # No tool calls: the LLM produced the final answer directly.
        current_turn_messages_final = _get_current_turn_messages(state)
        # Include the new response in tool collection.
        all_turn_messages = list(current_turn_messages_final) + [response]
        tools_used = _collect_tools_used(all_turn_messages)
        final_text = _content_to_text(response.content).strip()
        return Command(
            update={
                "messages": [response],
                "final_answer": final_text,
                "tools_used": tools_used,
            },
            goto="__end__",
        )

    def scope_guard_node(state: AnalyticsGraphState) -> dict[str, Any]:
        """Emits the short-circuit answer set by the router. No LLM involved."""
        preset_answer = state.get("final_answer", "")
        return {
            "final_answer": preset_answer,
            "tools_used": [],
        }

    def insight_synthesizer_node(state: AnalyticsGraphState) -> dict[str, Any]:
        """Synthesizes strategic/diagnostic follow-up answers using a plain LLM."""
        current_turn_messages = _get_current_turn_messages(state)
        router_decision = _deserialize_router_decision(state.get("router_decision"))
        tools_used = _collect_tools_used(current_turn_messages)

        if router_decision is not None and router_decision.intent in {
            "strategy_follow_up",
            "diagnostic_follow_up",
        }:
            question = _resolve_effective_question(state)
            strategy_context = _build_strategy_follow_up_context(state)
            if strategy_context is None:
                return {
                    "final_answer": OUT_OF_SCOPE_MESSAGE,
                    "tools_used": tools_used,
                }

            try:
                synthesized_response = cast(
                    AIMessage,
                    resolved_response_llm.invoke(
                        [
                            SystemMessage(
                                content=(
                                    STRATEGY_FOLLOW_UP_SYSTEM_PROMPT
                                    if router_decision.intent == "strategy_follow_up"
                                    else DIAGNOSTIC_FOLLOW_UP_SYSTEM_PROMPT
                                )
                            ),
                            HumanMessage(
                                content=(
                                    f"Pergunta de follow-up:\n{question}\n\n"
                                    f"Contexto analitico anterior:\n{strategy_context}"
                                )
                            ),
                        ]
                    ),
                )
            except Exception as exc:
                if is_llm_timeout_error(exc):
                    raise LlmTimeoutError(
                        "Tempo limite excedido ao sintetizar o follow-up contextual.",
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
            "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
            "tools_used": tools_used,
        }

    graph = StateGraph(AnalyticsGraphState)
    def tool_executor_node(state: AnalyticsGraphState) -> dict[str, Any]:
        """Execute all tool_calls from the last AIMessage and return ToolMessages."""
        messages = list(state.get("messages", []))
        # Find the last AIMessage that contains tool_calls.
        last_ai_message: AIMessage | None = None
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.tool_calls:
                last_ai_message = message
                break

        if last_ai_message is None:
            return {
                "messages": [
                    ToolMessage(
                        tool_call_id="no-tool-calls",
                        name="unknown",
                        status="error",
                        content="Nenhum tool_call encontrado na ultima mensagem do agente.",
                    )
                ],
                "debug_errors": [
                    _build_debug_error(
                        "tool_executor",
                        message="Nenhum tool_call encontrado na ultima AIMessage.",
                    )
                ],
            }

        tool_messages: list[ToolMessage] = []
        debug_errors: list[dict[str, Any]] = []

        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call.get("id") or tool_name
            tool = tools_by_name.get(tool_name)

            if tool is None:
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        status="error",
                        content=f"Tool nao registrada: {tool_name}.",
                    )
                )
                debug_errors.append(
                    _build_debug_error(
                        "tool_executor",
                        message=f"Tool nao registrada: {tool_name}.",
                        tool_name=tool_name,
                    )
                )
                continue

            try:
                result = tool.invoke(tool_args)
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        content=json.dumps(result, ensure_ascii=False, indent=2, default=str),
                        artifact=result,
                    )
                )
            except Exception as exc:
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        status="error",
                        content=(
                            f"Falha ao executar {tool_name}: {_stringify_exception(exc)}"
                        ),
                    )
                )
                debug_errors.append(
                    _build_debug_error(
                        "tool_executor",
                        message=_stringify_exception(exc),
                        error_type=type(exc).__name__,
                        tool_name=tool_name,
                    )
                )

        result_state: dict[str, Any] = {"messages": tool_messages}
        if debug_errors:
            result_state["debug_errors"] = debug_errors
        return result_state

    graph = StateGraph(AnalyticsGraphState)
    graph.add_node("router", router_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("scope_guard", scope_guard_node)
    graph.add_node("insight_synthesizer", insight_synthesizer_node)

    graph.add_edge(START, "router")
    # tool_executor loops back to agent after executing the tool call.
    graph.add_edge("tool_executor", "agent")
    graph.add_edge("scope_guard", END)
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
