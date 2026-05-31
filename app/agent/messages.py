from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, ToolMessage

from app.agent.state import AnalyticsGraphState

EMPTY_QUESTION_MESSAGE = (
    "Envie uma pergunta sobre trafego ou receita por canal para eu montar a analise."
)
INVALID_DATES_MESSAGE = (
    "As datas informadas sao invalidas. Use datas reais em YYYY-MM-DD, DD/MM/AAAA, "
    "DD/MM/AA ou periodos relativos suportados, por exemplo 2024-01-01 ate "
    "2024-01-31, 01/04/2026 ate 20/04/2026, 01/04/26 ou ultimos 7 dias."
)
MISSING_DATES_MESSAGE = (
    "Preciso que voce informe o periodo para eu consultar os dados. Voce pode usar "
    "YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou periodos relativos como ontem, este "
    "mes, ultimo mes e ultimos 7 dias."
)
OUT_OF_SCOPE_MESSAGE = (
    "Consigo ajudar apenas com analises de trafego, pedidos e receita por canal "
    "no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA "
    "ou com periodos relativos suportados."
)
UNSUPPORTED_DIMENSION_MESSAGE = (
    "No MVP atual eu so consigo analisar trafego, pedidos e receita por canal "
    "(traffic_source). Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA "
    "ou com periodos relativos suportados."
)
TEMPORARY_LLM_FAILURE_MESSAGE = (
    "Nao consegui concluir a analise agora por uma falha temporaria. Tente novamente em instantes."
)
TEMPORARY_TOOL_FAILURE_MESSAGE = (
    "Nao consegui consultar os dados agora por uma falha temporaria. Tente novamente em instantes."
)


def content_to_text(content: Any) -> str:
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


def _collect_tool_messages(messages: list[AnyMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


def _is_successful_tool_message(message: AnyMessage) -> bool:
    return isinstance(message, ToolMessage) and message.status != "error"


def _get_last_human_question(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            question = content_to_text(message.content).strip()
            if question:
                return question
    return ""


def _resolve_turn_start_index(state: AnalyticsGraphState) -> int:
    messages = list(state.get("messages", []))
    explicit_question = state.get("question", "").strip()

    if explicit_question:
        if messages and isinstance(messages[-1], HumanMessage):
            last_human_content = content_to_text(messages[-1].content).strip()
            if last_human_content == explicit_question:
                return len(messages) - 1
        return len(messages)

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index

    return len(messages)


def get_current_turn_messages(state: AnalyticsGraphState) -> list[AnyMessage]:
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
            last_human_content = content_to_text(last_message.content).strip()
            if last_human_content == explicit_question:
                return []
        return [HumanMessage(content=explicit_question)]

    if not existing_messages:
        return [HumanMessage(content=question)]

    return []


def _resolve_question(state: AnalyticsGraphState) -> str:
    question = state.get("question", "").strip()
    if question:
        return question

    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            content = content_to_text(message.content).strip()
            if content:
                return content

    return ""


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


def _build_temporary_failure_ai_message() -> AIMessage:
    return AIMessage(content=TEMPORARY_LLM_FAILURE_MESSAGE)
