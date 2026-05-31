from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
import inspect
import json
import re
import unicodedata
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import message_chunk_to_message
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from app.infra.llm import (
    LlmTimeoutError,
    build_tool_enabled_llm,
    is_llm_timeout_error,
)
from app.graph.date_normalizer import (
    _extract_relative_date_range,
    question_contains_temporal_signal,
)
from app.graph.llm_router import build_router_thread_context, classify_question
from app.graph.prompts import build_conversation_system_prompt
from app.graph.tools import get_analytics_tools
from app.schemas.router import RouterDecision
from app.infra.config import Settings
from app.infra.env import get_settings

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


class ToolExecutionError(RuntimeError):
    """Raised when the graph cannot complete a tool call safely."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "tool_executor",
        error_type: str | None = None,
        tool_name: str | None = None,
        debug_message: str | None = None,
        resolved_question: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.error_type = error_type
        self.tool_name = tool_name
        self.debug_message = debug_message or message
        self.resolved_question = resolved_question


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


async def _invoke_agent_llm(
    llm: Any,
    llm_input: list[AnyMessage],
    config: RunnableConfig | None = None,
) -> AIMessage:
    """Return one complete AI response, streaming when the model supports it.

    Streaming here solves two problems at once: the graph can surface provider
    chunks through LangGraph's event stream, and the node still ends with a
    normal `AIMessage` that preserves the current tool-calling loop.

    `config` must be the RunnableConfig received by the node so that
    LangGraph's astream_events callbacks are wired into the LLM call.
    Without it, on_chat_model_stream events are never emitted and the CLI
    receives the full response only at the end.
    """
    astream = getattr(llm, "astream", None)
    if not callable(astream):
        return cast(AIMessage, llm.invoke(llm_input))

    streamed_chunk: AIMessageChunk | None = None
    streamed_message: AIMessage | None = None
    # Real LangChain runnables (ChatOpenAI, ChatAnthropic, RunnableBinding from
    # bind_tools) accept config and propagate callbacks so astream_events can
    # capture on_chat_model_stream for each token.  Test fakes (FakeAgentLLM)
    # are plain Python classes — not Runnable — and do not accept config.
    if isinstance(llm, Runnable) and config is not None:
        event_stream = cast(AsyncIterator[Any], astream(llm_input, config=config))
    else:
        event_stream = cast(AsyncIterator[Any], astream(llm_input))
    async for chunk in event_stream:
        if isinstance(chunk, AIMessageChunk):
            streamed_chunk = chunk if streamed_chunk is None else streamed_chunk + chunk
            continue
        if isinstance(chunk, AIMessage):
            streamed_message = chunk

    if streamed_chunk is not None:
        return cast(AIMessage, message_chunk_to_message(streamed_chunk))
    if streamed_message is not None:
        return streamed_message

    return cast(AIMessage, llm.invoke(llm_input))


def _build_agent_llm_input(
    state: AnalyticsGraphState,
    *,
    agent_system_prompt: str,
) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """Assemble the LLM input and current-turn history for one agent step."""
    current_turn_messages = get_current_turn_messages(state)
    resolved_question = _resolve_effective_question(state)
    router_decision = _deserialize_router_decision(state.get("router_decision"))
    if resolved_question:
        rest_of_turn: list[AnyMessage] = list(current_turn_messages)
        if rest_of_turn and isinstance(rest_of_turn[0], HumanMessage):
            rest_of_turn = rest_of_turn[1:]
        agent_turn_messages: list[AnyMessage] = [HumanMessage(content=resolved_question)]
        agent_turn_messages.extend(rest_of_turn)
    else:
        agent_turn_messages = list(current_turn_messages)

    llm_input: list[AnyMessage] = [SystemMessage(content=agent_system_prompt)]
    router_guidance = _build_router_guidance_message(
        router_decision,
        resolved_question=resolved_question,
    )
    if router_guidance is not None:
        llm_input.append(SystemMessage(content=router_guidance))
    llm_input.extend(_build_follow_up_system_messages(state, router_decision))
    llm_input.extend(agent_turn_messages)
    return llm_input, current_turn_messages


def _build_agent_error_command(
    state: AnalyticsGraphState,
    exc: Exception,
) -> Command[Literal["tool_executor", "__end__"]]:
    """Convert unexpected agent failures into the graph's safe final state."""
    current_turn_messages_for_error = get_current_turn_messages(state)
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


def _build_agent_response_command(
    current_turn_messages: list[AnyMessage],
    response: AIMessage,
) -> Command[Literal["tool_executor", "__end__"]]:
    """Route the agent turn either to tool execution or to the final answer."""
    if response.tool_calls:
        return Command(
            update={"messages": [response]},
            goto="tool_executor",
        )

    all_turn_messages = list(current_turn_messages) + [response]
    tools_used = _collect_tools_used(all_turn_messages)
    final_text = content_to_text(response.content).strip()
    return Command(
        update={
            "messages": [response],
            "final_answer": final_text,
            "tools_used": tools_used,
        },
        goto="__end__",
    )


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


def _resolve_effective_question(state: AnalyticsGraphState) -> str:
    resolved_question = state.get("resolved_question", "").strip()
    if resolved_question:
        return resolved_question
    return _resolve_question(state)


def _normalize_loose_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _collect_tool_messages(messages: list[AnyMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


def _is_successful_tool_message(message: AnyMessage) -> bool:
    return isinstance(message, ToolMessage) and message.status != "error"


def _get_last_human_question(messages: list[AnyMessage]) -> str:
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
        previous_question = content_to_text(previous_turn_messages[0].content).strip()

    previous_answer = ""
    for message in reversed(previous_turn_messages):
        if not isinstance(message, AIMessage):
            continue
        previous_answer = content_to_text(message.content).strip()
        if previous_answer:
            break

    tool_context_blocks = [
        f"Tool: {message.name}\nResultado:\n{content_to_text(message.content)}"
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


def _build_follow_up_system_messages(
    state: AnalyticsGraphState,
    router_decision: RouterDecision | None,
) -> list[SystemMessage]:
    if router_decision is None or router_decision.intent not in {
        "strategy_follow_up",
        "diagnostic_follow_up",
    }:
        return []

    follow_up_context = _build_strategy_follow_up_context(state)
    if follow_up_context is None:
        return []

    return [
        SystemMessage(
            content=(
                "Contexto analitico anterior do mesmo thread:\n"
                f"{follow_up_context}\n\n"
                "Use esse contexto para responder o follow-up sem inventar fatos. "
                "Se o contexto atual ja for suficiente, responda diretamente sem "
                "tool_call. Se realmente precisar de novos dados dentro do schema, "
                "voce pode chamar uma tool."
            )
        ),
    ]


def _build_router_guidance_message(
    router_decision: RouterDecision | None,
    *,
    resolved_question: str,
) -> str | None:
    if router_decision is None:
        return None

    normalized_params = router_decision.normalized_params
    guidance_lines = [
        "Contexto estruturado do router para este turno:",
        f"- pergunta canonica: {resolved_question or '(vazia)'}",
        f"- intent: {router_decision.intent}",
        f"- traffic_source: {normalized_params.traffic_source or 'agregado/todos os canais'}",
        (
            f"- start_date: {normalized_params.start_date.isoformat()}"
            if normalized_params.start_date is not None
            else "- start_date: nao resolvida"
        ),
        (
            f"- end_date: {normalized_params.end_date.isoformat()}"
            if normalized_params.end_date is not None
            else "- end_date: nao resolvida"
        ),
    ]

    if (
        not router_decision.needs_clarification
        and router_decision.refusal_reason is None
        and router_decision.intent in {"traffic_volume", "channel_performance"}
    ):
        guidance_lines.append(
            "- o router ja resolveu a intencao e os parametros necessarios; nao peca nova clarificacao sobre periodo, metrica ou comparacao por canal"
        )

    if (
        not router_decision.needs_clarification
        and router_decision.refusal_reason is None
        and router_decision.intent == "ambiguous_analytics"
    ):
        guidance_lines.append(
            "- a pergunta esta no dominio, mas ainda esta ambigua entre volume de usuarios e performance financeira; antes de qualquer tool_call, peca uma clarificacao curta e objetiva"
        )

    return "\n".join(guidance_lines)


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


def _apply_date_normalizer(question: str, decision: RouterDecision) -> RouterDecision:
    """Post-process the LLM router decision with deterministic date resolution.

    The LLM is told not to infer dates, so it leaves start_date/end_date null for
    relative expressions like "ultimo mes". This function fills them in using the
    deterministic date normalizer and clears missing_dates if resolution succeeds.
    """
    if not question_contains_temporal_signal(question):
        return decision

    date_range, _ = _extract_relative_date_range(question)
    if date_range is None:
        # Temporal signal detected but normalizer couldn't resolve (e.g. explicit
        # dates the LLM already handled) — only override if both dates still null.
        if decision.start_date is not None or decision.end_date is not None:
            return decision
        return decision

    resolved_start, resolved_end = date_range
    needs_clarification = decision.needs_clarification
    clarification_reason = decision.clarification_reason
    response_message = decision.response_message

    # Clear missing_dates if the normalizer resolved the period.
    if needs_clarification and clarification_reason == "missing_dates":
        needs_clarification = False
        clarification_reason = None
        response_message = None

    return RouterDecision(
        intent=decision.intent,
        traffic_source=decision.traffic_source,
        start_date=decision.start_date if decision.start_date is not None else resolved_start,
        end_date=decision.end_date if decision.end_date is not None else resolved_end,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        refusal_reason=decision.refusal_reason,
        response_message=response_message,
    )


def _inherit_dates_from_thread(
    thread_context: list[BaseMessage], decision: RouterDecision
) -> RouterDecision:
    """Inherit temporal context from the most recent human message that had a date.

    Handles two cases:
    - Turn N had dates + metric clarification → turn N+1 resolves metric without repeating date.
    - Turn N had dates + tool executed → turn N+1 asks about same scope without repeating date.
    """
    for msg in reversed(thread_context):
        if not isinstance(msg, HumanMessage):
            continue
        text = msg.content if isinstance(msg.content, str) else ""
        if not question_contains_temporal_signal(text):
            continue
        date_range, _ = _extract_relative_date_range(text)
        if date_range is None:
            continue
        resolved_start, resolved_end = date_range
        return RouterDecision(
            intent=decision.intent,
            traffic_source=decision.traffic_source,
            start_date=resolved_start,
            end_date=resolved_end,
            needs_clarification=False,
            clarification_reason=None,
            refusal_reason=decision.refusal_reason,
            response_message=None,
        )
    return decision


def _resolve_router_turn(
    state: AnalyticsGraphState,
    question: str,
    settings: Settings | None = None,
    router_llm: Any | None = None,
) -> tuple[str, RouterDecision]:
    thread_context = build_router_thread_context(list(state.get("messages", [])))
    decision = classify_question(
        question,
        thread_context=thread_context,
        settings=settings,
        _router_runnable=router_llm,
    )
    decision = _apply_date_normalizer(question, decision)
    if decision.needs_clarification and decision.clarification_reason == "missing_dates":
        decision = _inherit_dates_from_thread(thread_context, decision)
    return question, decision


def _count_agent_iterations_in_turn(state: AnalyticsGraphState) -> int:
    """Count how many times the agent node has run in the current turn."""
    current_turn_messages = get_current_turn_messages(state)
    return sum(
        1 for msg in current_turn_messages
        if isinstance(msg, AIMessage) and msg.tool_calls
    )


def _build_iteration_limit_command(
    state: AnalyticsGraphState,
) -> Command[Literal["tool_executor", "__end__"]]:
    current_turn_messages = get_current_turn_messages(state)
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


def build_analytics_graph(
    settings: Settings | None = None,
    *,
    agent_llm: Any | None = None,
    router_llm: Any | None = None,
    tools: tuple[BaseTool, ...] | None = None,
    checkpointer: BaseCheckpointSaver | bool | None = None,
) -> Any:
    analytics_tools = tools or get_analytics_tools()
    resolved_agent_llm = agent_llm or build_tool_enabled_llm(settings)
    tools_by_name: dict[str, BaseTool] = {tool.name: tool for tool in analytics_tools}
    agent_system_prompt = build_conversation_system_prompt()

    def preprocess_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["agent", "__end__"]]:
        question = _resolve_question(state)
        turn_start_index = _resolve_turn_start_index(state)
        injected_messages = _build_turn_question_messages(state)

        # Guard: short-circuit before any LLM call when there is no question.
        if not question:
            empty_decision = RouterDecision(
                intent="out_of_scope",
                refusal_reason="empty_question",
                response_message=EMPTY_QUESTION_MESSAGE,
            )
            return Command(
                update={
                    "router_decision": _serialize_router_decision(empty_decision),
                    "resolved_question": "",
                    "turn_start_index": turn_start_index,
                    "debug_errors": [],
                    "final_answer": EMPTY_QUESTION_MESSAGE,
                    "tools_used": [],
                },
                goto="__end__",
            )

        resolved_question, router_decision = _resolve_router_turn(state, question, settings, router_llm)
        serialized_router_decision = _serialize_router_decision(router_decision)
        state_update: dict[str, Any] = {
            "router_decision": serialized_router_decision,
            "resolved_question": resolved_question,
            "turn_start_index": turn_start_index,
            "debug_errors": [],
        }

        if injected_messages:
            state_update["messages"] = injected_messages

        # Structural short-circuits still end the turn before the agent.
        if _router_decision_short_circuits(router_decision):
            state_update["final_answer"] = (
                router_decision.response_message or EMPTY_QUESTION_MESSAGE
            )
            state_update["tools_used"] = []
            return Command(update=state_update, goto="__end__")

        # Everything else flows through the tool-enabled agent.
        return Command(update=state_update, goto="agent")

    def agent_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["tool_executor", "__end__"]]:
        """Synchronous agent path used by `invoke()` based executions."""
        if _count_agent_iterations_in_turn(state) >= _MAX_AGENT_ITERATIONS:
            return _build_iteration_limit_command(state)

        llm_input, current_turn_messages = _build_agent_llm_input(
            state,
            agent_system_prompt=agent_system_prompt,
        )

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
            return _build_agent_error_command(state, exc)

        return _build_agent_response_command(current_turn_messages, response)

    async def agent_node_async(
        state: AnalyticsGraphState,
        config: RunnableConfig | None = None,
    ) -> Command[Literal["tool_executor", "__end__"]]:
        """LLM agent that decides which tool to call, then synthesizes the final answer."""
        if _count_agent_iterations_in_turn(state) >= _MAX_AGENT_ITERATIONS:
            return _build_iteration_limit_command(state)

        llm_input, current_turn_messages = _build_agent_llm_input(
            state,
            agent_system_prompt=agent_system_prompt,
        )

        try:
            response = await _invoke_agent_llm(resolved_agent_llm, llm_input, config=config)
        except Exception as exc:
            if is_llm_timeout_error(exc):
                raise LlmTimeoutError(
                    "Tempo limite excedido no nó agente.",
                    source="agent",
                    error_type=type(exc).__name__,
                    debug_message=_stringify_exception(exc),
                ) from exc
            return _build_agent_error_command(state, exc)

        return _build_agent_response_command(current_turn_messages, response)

    def tool_executor_node(state: AnalyticsGraphState) -> dict[str, Any]:
        """Execute all tool_calls from the last AIMessage and return ToolMessages."""
        messages = list(state.get("messages", []))
        resolved_question = _resolve_effective_question(state)
        # Find the last AIMessage that contains tool_calls.
        last_ai_message: AIMessage | None = None
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.tool_calls:
                last_ai_message = message
                break

        if last_ai_message is None:
            raise ToolExecutionError(
                TEMPORARY_TOOL_FAILURE_MESSAGE,
                error_type="MissingToolCallError",
                debug_message="Nenhum tool_call encontrado na ultima AIMessage.",
                resolved_question=resolved_question,
            )

        tool_messages: list[ToolMessage] = []
        debug_errors: list[dict[str, Any]] = []

        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call.get("id") or tool_name
            tool = tools_by_name.get(tool_name)

            if tool is None:
                raise ToolExecutionError(
                    TEMPORARY_TOOL_FAILURE_MESSAGE,
                    error_type="UnknownToolError",
                    tool_name=tool_name,
                    debug_message=f"Tool nao registrada: {tool_name}.",
                    resolved_question=resolved_question,
                )

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
                raise ToolExecutionError(
                    TEMPORARY_TOOL_FAILURE_MESSAGE,
                    error_type=type(exc).__name__,
                    tool_name=tool_name,
                    debug_message=_stringify_exception(exc),
                    resolved_question=resolved_question,
                ) from exc

        result_state: dict[str, Any] = {"messages": tool_messages}
        if debug_errors:
            result_state["debug_errors"] = debug_errors
        return result_state

    graph = StateGraph(AnalyticsGraphState)
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("agent", RunnableLambda(agent_node, afunc=agent_node_async, name="agent"))
    graph.add_node("tool_executor", tool_executor_node)

    graph.add_edge(START, "preprocess")
    # tool_executor loops back to agent after executing the tool call.
    graph.add_edge("tool_executor", "agent")

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
    """Execute one analytics turn synchronously and return the final graph state.

    This is the compatibility entrypoint used by the current `/query` endpoint.
    It reuses `_prepare_graph_run()` so the sync path and the streaming path
    build the exact same graph input and configurable thread context.
    """
    resolved_graph, input_state, config = _prepare_graph_run(
        question,
        settings=settings,
        thread_id=thread_id,
        graph=graph,
    )

    return cast(AnalyticsGraphState, resolved_graph.invoke(input_state, config=config))


def _prepare_graph_run(
    question: str,
    settings: Settings | None = None,
    *,
    thread_id: str | None = None,
    graph: Any | None = None,
) -> tuple[Any, AnalyticsGraphState, dict[str, Any] | None]:
    """Build the common execution artifacts for one graph turn.

    Returns the resolved graph instance, the per-turn input state, and the
    optional LangGraph configurable context used for checkpoint/thread
    continuity. Centralizing this logic keeps `invoke()` and
    `astream_events()` behavior aligned.
    """
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

    return resolved_graph, input_state, config


async def astream_analytics_graph_events(
    question: str,
    settings: Settings | None = None,
    *,
    thread_id: str | None = None,
    graph: Any | None = None,
    version: Literal["v1", "v2", "v3"] = "v3",
    **kwargs: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Stream LangGraph execution events for a single analytics turn.

    This keeps the exact same input/config preparation used by the synchronous
    invoke path, but delegates execution to LangGraph's `astream_events`.
    """
    resolved_graph, input_state, config = _prepare_graph_run(
        question,
        settings=settings,
        thread_id=thread_id,
        graph=graph,
    )

    event_stream = resolved_graph.astream_events(
        input_state,
        config=config,
        version=version,
        **kwargs,
    )
    if inspect.isawaitable(event_stream):
        event_stream = await event_stream

    async for event in event_stream:
        yield cast(dict[str, Any], event)


__all__ = [
    "AnalyticsGraphState",
    "INVALID_DATES_MESSAGE",
    "MISSING_DATES_MESSAGE",
    "OUT_OF_SCOPE_MESSAGE",
    "TEMPORARY_LLM_FAILURE_MESSAGE",
    "TEMPORARY_TOOL_FAILURE_MESSAGE",
    "ToolExecutionError",
    "UNSUPPORTED_DIMENSION_MESSAGE",
    "build_analytics_graph",
    "content_to_text",
    "get_current_turn_messages",
    "get_persistent_analytics_graph",
    "astream_analytics_graph_events",
    "invoke_analytics_graph",
]
