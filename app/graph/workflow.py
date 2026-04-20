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

from app.graph.llm import (
    LlmTimeoutError,
    build_analytics_llm,
    build_tool_enabled_llm,
    is_llm_timeout_error,
)
from app.graph.prompts import (
    FINAL_RESPONSE_SYSTEM_PROMPT,
    build_conversation_system_prompt,
)
from app.graph.router import (
    EMPTY_QUESTION_MESSAGE,
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    build_router_decision,
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
    router_decision: RouterDecision
    next_step: Literal["conversation", "tools", "final_response"]
    turn_start_index: int
    final_answer: str
    tools_used: list[str]


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


def _get_last_ai_message(messages: list[AnyMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _collect_tool_messages(messages: list[AnyMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


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


def build_analytics_graph(
    settings: Settings | None = None,
    *,
    tool_enabled_llm: Any | None = None,
    response_llm: Any | None = None,
    tools: tuple[BaseTool, ...] | None = None,
    checkpointer: BaseCheckpointSaver | bool | None = None,
) -> Any:
    analytics_tools = tools or get_analytics_tools()
    tools_by_name = {tool.name: tool for tool in analytics_tools}
    conversation_llm = tool_enabled_llm or build_tool_enabled_llm(settings)
    synthesis_llm = response_llm or build_analytics_llm(settings)
    conversation_system_prompt = build_conversation_system_prompt()

    def router_node(state: AnalyticsGraphState) -> dict[str, Any]:
        question = _resolve_question(state)
        turn_start_index = _resolve_turn_start_index(state)
        injected_messages = _build_turn_question_messages(state)
        router_decision = build_router_decision(question)

        if router_decision.needs_clarification or router_decision.refusal_reason is not None:
            return {
                "messages": injected_messages,
                "router_decision": router_decision,
                "final_answer": router_decision.response_message or EMPTY_QUESTION_MESSAGE,
                "next_step": "final_response",
                "turn_start_index": turn_start_index,
            }

        return {
            "router_decision": router_decision,
            "next_step": "conversation",
            "turn_start_index": turn_start_index,
        }

    def conversation_node(state: AnalyticsGraphState) -> dict[str, Any]:
        existing_messages = list(state.get("messages", []))
        injected_messages = _build_turn_question_messages(state)

        if injected_messages:
            existing_messages = [*existing_messages, *injected_messages]

        try:
            response = cast(
                AIMessage,
                conversation_llm.invoke(
                    [SystemMessage(content=conversation_system_prompt), *existing_messages]
                ),
            )
        except Exception as exc:
            if is_llm_timeout_error(exc):
                raise LlmTimeoutError("Tempo limite excedido ao consultar o LLM.") from exc
            return {
                "messages": [*injected_messages, _build_temporary_failure_ai_message()],
                "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
            }

        return {"messages": [*injected_messages, response]}

    def execute_tools_node(state: AnalyticsGraphState) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        last_ai_message = _get_last_ai_message(messages)
        if last_ai_message is None or not last_ai_message.tool_calls:
            return {}

        tool_messages: list[ToolMessage] = []

        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call["name"]
            tool_call_id = str(tool_call.get("id") or tool_name)
            tool = tools_by_name.get(tool_name)

            if tool is None:
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        status="error",
                        content=f"Tool desconhecida solicitada pelo modelo: {tool_name}.",
                    )
                )
                continue

            try:
                result = tool.invoke(tool_call)
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        content=_serialize_tool_result(result),
                        artifact=result,
                    )
                )
            except Exception as exc:
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        status="error",
                        content=f"Falha temporaria ao executar {tool_name}: {exc}",
                    )
                )

        return {"messages": tool_messages}

    def final_response_node(state: AnalyticsGraphState) -> dict[str, Any]:
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
            question = _resolve_question(state)
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
                        "Tempo limite excedido ao sintetizar a resposta final."
                    ) from exc
                return {
                    "messages": [_build_temporary_failure_ai_message()],
                    "final_answer": TEMPORARY_LLM_FAILURE_MESSAGE,
                    "tools_used": tools_used,
                }
            return {
                "messages": [synthesized_response],
                "final_answer": _content_to_text(synthesized_response.content).strip(),
                "tools_used": tools_used,
            }

        last_ai_message = _get_last_ai_message(current_turn_messages)
        if last_ai_message is None:
            return {
                "final_answer": EMPTY_QUESTION_MESSAGE,
                "tools_used": tools_used,
            }

        return {
            "final_answer": _content_to_text(last_ai_message.content).strip(),
            "tools_used": tools_used,
        }

    def route_after_router(
        state: AnalyticsGraphState,
    ) -> Literal["conversation", "final_response"]:
        router_decision = state.get("router_decision")
        if (
            router_decision is not None
            and (
                router_decision.needs_clarification
                or router_decision.refusal_reason is not None
            )
        ):
            return "final_response"

        return cast(
            Literal["conversation", "final_response"],
            state.get("next_step", "final_response"),
        )

    def route_after_conversation(
        state: AnalyticsGraphState,
    ) -> Literal["tools", "final_response"]:
        last_ai_message = _get_last_ai_message(list(state.get("messages", [])))
        if last_ai_message and last_ai_message.tool_calls:
            return "tools"
        return "final_response"

    graph = StateGraph(AnalyticsGraphState)
    graph.add_node("router", router_node)
    graph.add_node("conversation", conversation_node)
    graph.add_node("tools", execute_tools_node)
    graph.add_node("final_response", final_response_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "conversation": "conversation",
            "final_response": "final_response",
        },
    )
    graph.add_conditional_edges(
        "conversation",
        route_after_conversation,
        {
            "tools": "tools",
            "final_response": "final_response",
        },
    )
    graph.add_edge("tools", "final_response")
    graph.add_edge("final_response", END)

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
