from __future__ import annotations

import json
import re
import unicodedata
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.graph.llm import build_analytics_llm, build_tool_enabled_llm
from app.graph.prompts import (
    FINAL_RESPONSE_SYSTEM_PROMPT,
    build_conversation_system_prompt,
)
from app.graph.tools import get_analytics_tools
from app.utils.config import Settings

DATE_TOKEN_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
QUESTION_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
SUPPORTED_CHANNEL_TOKENS = frozenset(
    {
        "canal",
        "canais",
        "channel",
        "channels",
    }
)
SUPPORTED_VOLUME_SIGNAL_TOKENS = frozenset(
    {
        "trafego",
        "traffic",
        "volume",
    }
)
SUPPORTED_USER_METRIC_TOKENS = frozenset(
    {
        "usuario",
        "usuarios",
        "user",
        "users",
    }
)
SUPPORTED_PERFORMANCE_METRIC_TOKENS = frozenset(
    {
        "pedido",
        "pedidos",
        "order",
        "orders",
        "receita",
        "revenue",
        "ranking",
        "performance",
        "desempenho",
        "melhor",
        "top",
    }
)
SUPPORTED_SOURCE_TOKENS = frozenset(
    {
        "search",
        "organic",
        "facebook",
        "instagram",
    }
)
UNSUPPORTED_METRIC_TOKENS = frozenset(
    {
        "cac",
        "roas",
        "roi",
        "ltv",
        "ctr",
        "cpc",
        "cpm",
        "impressao",
        "impressoes",
        "impression",
        "impressions",
        "clique",
        "cliques",
        "click",
        "clicks",
        "campanha",
        "campanhas",
        "campaign",
        "campaigns",
        "anuncio",
        "anuncios",
        "ad",
        "ads",
        "criativo",
        "criativos",
        "creative",
        "creatives",
        "empresa",
        "empresas",
        "company",
        "companies",
    }
)

MISSING_DATES_MESSAGE = (
    "Preciso que voce informe start_date e end_date no formato YYYY-MM-DD para eu "
    "consultar os dados. Exemplo: 2024-01-01 ate 2024-01-31."
)
EMPTY_QUESTION_MESSAGE = (
    "Envie uma pergunta sobre trafego ou receita por canal para eu montar a analise."
)
TEMPORARY_LLM_FAILURE_MESSAGE = (
    "Nao consegui concluir a analise agora por uma falha temporaria. Tente novamente em instantes."
)
TEMPORARY_TOOL_FAILURE_MESSAGE = (
    "Nao consegui consultar os dados agora por uma falha temporaria. Tente novamente em instantes."
)


class AnalyticsGraphState(TypedDict, total=False):
    question: str
    messages: Annotated[list[AnyMessage], add_messages]
    next_step: Literal["conversation", "tools", "final_response"]
    final_answer: str
    tools_used: list[str]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).lower()


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


def _extract_iso_dates(question: str) -> list[str]:
    return DATE_TOKEN_PATTERN.findall(question)


def _extract_question_tokens(question: str) -> set[str]:
    return set(QUESTION_TOKEN_PATTERN.findall(_normalize_text(question)))


def _question_supports_date_clarification(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    has_performance_metric = bool(
        question_tokens & SUPPORTED_PERFORMANCE_METRIC_TOKENS
    )
    has_user_metric = bool(question_tokens & SUPPORTED_USER_METRIC_TOKENS)
    has_channel_context = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
        )
    )

    return has_performance_metric or (has_user_metric and has_channel_context)


def _get_last_ai_message(messages: list[AnyMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _get_last_human_message(messages: list[AnyMessage]) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None


def _collect_tool_messages(messages: list[AnyMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


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
) -> Any:
    analytics_tools = tools or get_analytics_tools()
    tools_by_name = {tool.name: tool for tool in analytics_tools}
    conversation_llm = tool_enabled_llm or build_tool_enabled_llm(settings)
    synthesis_llm = response_llm or build_analytics_llm(settings)
    conversation_system_prompt = build_conversation_system_prompt()

    def router_node(state: AnalyticsGraphState) -> dict[str, Any]:
        question = _resolve_question(state)
        if not question:
            return {
                "final_answer": EMPTY_QUESTION_MESSAGE,
                "next_step": "final_response",
            }

        if (
            _question_supports_date_clarification(question)
            and len(_extract_iso_dates(question)) < 2
        ):
            return {
                "final_answer": MISSING_DATES_MESSAGE,
                "next_step": "final_response",
            }

        return {"next_step": "conversation"}

    def conversation_node(state: AnalyticsGraphState) -> dict[str, Any]:
        question = _resolve_question(state)
        explicit_question = state.get("question", "").strip()
        existing_messages = list(state.get("messages", []))
        injected_messages: list[AnyMessage] = []

        last_human_message = _get_last_human_message(existing_messages)
        if explicit_question and (
            last_human_message is None
            or _content_to_text(last_human_message.content).strip() != explicit_question
        ):
            injected_messages.append(HumanMessage(content=explicit_question))
        elif not existing_messages:
            injected_messages.append(HumanMessage(content=question))

        if injected_messages:
            existing_messages = [*existing_messages, *injected_messages]

        try:
            response = cast(
                AIMessage,
                conversation_llm.invoke(
                    [SystemMessage(content=conversation_system_prompt), *existing_messages]
                ),
            )
        except Exception:
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
        messages = list(state.get("messages", []))
        tools_used = _collect_tools_used(messages)
        preset_answer = state.get("final_answer")
        tool_messages = _collect_tool_messages(messages)

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
            except Exception:
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

        last_ai_message = _get_last_ai_message(messages)
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

    return graph.compile()


def invoke_analytics_graph(
    question: str,
    settings: Settings | None = None,
) -> AnalyticsGraphState:
    graph = build_analytics_graph(settings)
    return cast(AnalyticsGraphState, graph.invoke({"question": question}))


__all__ = [
    "AnalyticsGraphState",
    "MISSING_DATES_MESSAGE",
    "TEMPORARY_LLM_FAILURE_MESSAGE",
    "TEMPORARY_TOOL_FAILURE_MESSAGE",
    "build_analytics_graph",
    "invoke_analytics_graph",
]
