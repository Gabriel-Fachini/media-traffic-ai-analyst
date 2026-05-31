from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import message_chunk_to_message
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.types import Command

from app.agent.messages import (
    EMPTY_QUESTION_MESSAGE,
    TEMPORARY_LLM_FAILURE_MESSAGE,
    TEMPORARY_TOOL_FAILURE_MESSAGE,
    _build_debug_error,
    _build_temporary_failure_ai_message,
    _build_turn_question_messages,
    _collect_tools_used,
    _get_last_human_question,
    _is_successful_tool_message,
    _resolve_question,
    _resolve_turn_start_index,
    _stringify_exception,
    content_to_text,
    get_current_turn_messages,
)
from app.agent.state import AnalyticsGraphState, ToolExecutionError
from app.core.router.date_resolution import apply_date_normalizer, inherit_dates_from_thread
from app.core.router.decision import RouterDecision
from app.infra.config import Settings
from app.infra.llm import LlmTimeoutError, is_llm_timeout_error

# Safety guard: max agent/tool iterations per turn to prevent infinite loops.
_MAX_AGENT_ITERATIONS = 3


async def _invoke_agent_llm(
    llm: Any,
    llm_input: list[AnyMessage],
    config: RunnableConfig | None = None,
) -> AIMessage:
    """Return one complete AI response, streaming when the model supports it."""
    astream = getattr(llm, "astream", None)
    if not callable(astream):
        return cast(AIMessage, llm.invoke(llm_input))

    streamed_chunk: AIMessageChunk | None = None
    streamed_message: AIMessage | None = None
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


def _resolve_effective_question(state: AnalyticsGraphState) -> str:
    resolved_question = state.get("resolved_question", "").strip()
    if resolved_question:
        return resolved_question
    return _resolve_question(state)


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


def _build_agent_llm_input(
    state: AnalyticsGraphState,
    *,
    agent_system_prompt: str,
) -> tuple[list[AnyMessage], list[AnyMessage]]:
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


def _count_agent_iterations_in_turn(state: AnalyticsGraphState) -> int:
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


def _resolve_router_turn(
    state: AnalyticsGraphState,
    question: str,
    settings: Settings | None = None,
    router_llm: Any | None = None,
) -> tuple[str, RouterDecision]:
    from app.core.router.classifier import build_router_thread_context, classify_question

    thread_context = build_router_thread_context(list(state.get("messages", [])))
    previous_router_decision = _deserialize_router_decision(state.get("router_decision"))
    decision = classify_question(
        question,
        thread_context=thread_context,
        settings=settings,
        _router_runnable=router_llm,
    )
    decision = apply_date_normalizer(question, decision)
    if (
        previous_router_decision is not None
        and previous_router_decision.needs_clarification
        and previous_router_decision.clarification_reason == "missing_dates"
    ):
        previous_question = _get_last_human_question(thread_context)
        if previous_question:
            combined_question = f"{previous_question.rstrip()} {question.strip()}".strip()
            combined_decision = classify_question(
                combined_question,
                thread_context=thread_context,
                settings=settings,
                _router_runnable=router_llm,
            )
            combined_decision = apply_date_normalizer(combined_question, combined_decision)
            if (
                not combined_decision.needs_clarification
                and combined_decision.refusal_reason is None
            ):
                return combined_question, combined_decision

    if decision.needs_clarification and decision.clarification_reason == "missing_dates":
        decision = inherit_dates_from_thread(
            thread_context,
            decision,
            previous_router_decision=previous_router_decision,
            previous_tools_used=state.get("tools_used", []),
        )
    return question, decision


def build_preprocess_node(
    settings: Settings | None,
    router_llm: Any | None,
) -> Any:
    def preprocess_node(
        state: AnalyticsGraphState,
    ) -> Command[Literal["agent", "__end__"]]:
        question = _resolve_question(state)
        turn_start_index = _resolve_turn_start_index(state)
        injected_messages = _build_turn_question_messages(state)

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
                    "router_llm_call_count": 0,
                    "tool_execution_count": 0,
                    "debug_errors": [],
                    "final_answer": EMPTY_QUESTION_MESSAGE,
                    "tools_used": [],
                },
                goto="__end__",
            )

        resolved_question, router_decision = _resolve_router_turn(
            state, question, settings, router_llm
        )
        serialized_router_decision = _serialize_router_decision(router_decision)
        state_update: dict[str, Any] = {
            "router_decision": serialized_router_decision,
            "resolved_question": resolved_question,
            "turn_start_index": turn_start_index,
            "router_llm_call_count": 1,
            "tool_execution_count": 0,
            "debug_errors": [],
        }

        if injected_messages:
            state_update["messages"] = injected_messages

        if _router_decision_short_circuits(router_decision):
            state_update["final_answer"] = (
                router_decision.response_message or EMPTY_QUESTION_MESSAGE
            )
            state_update["tools_used"] = []
            return Command(update=state_update, goto="__end__")

        return Command(update=state_update, goto="agent")

    return preprocess_node


def build_agent_nodes(
    resolved_agent_llm: Any,
    agent_system_prompt: str,
) -> tuple[Any, Any]:
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

    return agent_node, agent_node_async


def build_tool_executor_node(tools_by_name: dict[str, Any]) -> Any:
    import json as _json

    def tool_executor_node(state: AnalyticsGraphState) -> dict[str, Any]:
        """Execute all tool_calls from the last AIMessage and return ToolMessages."""
        messages = list(state.get("messages", []))
        resolved_question = _resolve_effective_question(state)
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
                        content=_json.dumps(result, ensure_ascii=False, indent=2, default=str),
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

        result_state: dict[str, Any] = {
            "messages": tool_messages,
            "tool_execution_count": int(state.get("tool_execution_count", 0) or 0)
            + len(tool_messages),
        }
        if debug_errors:
            result_state["debug_errors"] = debug_errors
        return result_state

    return tool_executor_node
