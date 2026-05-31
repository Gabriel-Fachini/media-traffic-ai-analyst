from __future__ import annotations

from time import perf_counter
from typing import cast

from fastapi.responses import JSONResponse
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.agent.graph import AnalyticsGraphState, ToolExecutionError
from app.agent.messages import get_current_turn_messages
from app.api.schemas import (
    AgentToolCall,
    DebugError,
    DebugInfo,
    ErrorResponse,
    QueryMetadata,
    QueryRequest,
    TokenUsage,
    TurnObservability,
)
from app.core.router.decision import RouterDecision
from app.infra.llm import LlmTimeoutError


def _extract_agent_tool_calls(state: AnalyticsGraphState) -> list[AgentToolCall]:
    calls: list[AgentToolCall] = []
    seen: set[str] = set()
    for message in get_current_turn_messages(state):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        for tc in message.tool_calls:
            key = f"{tc['name']}:{tc.get('id', '')}"
            if key in seen:
                continue
            seen.add(key)
            calls.append(
                AgentToolCall(
                    tool_name=tc["name"],
                    args={k: str(v) for k, v in tc.get("args", {}).items()},
                )
            )
    return calls


def _build_turn_observability(
    *,
    latency_ms: int | None,
    llm_call_count: int,
    tool_call_count: int,
    tools_used: list[str],
    token_usage: TokenUsage | None = None,
) -> TurnObservability:
    return TurnObservability(
        latency_ms=latency_ms,
        llm_call_count=llm_call_count,
        tool_call_count=tool_call_count,
        tools_used=tools_used,
        token_usage=token_usage or TokenUsage(),
    )


def _extract_turn_observability_from_state(
    state: AnalyticsGraphState,
    *,
    latency_ms: int | None,
) -> TurnObservability:
    current_turn_messages = get_current_turn_messages(state)
    llm_call_count = int(state.get("router_llm_call_count", 0) or 0)
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    for message in current_turn_messages:
        if not isinstance(message, AIMessage):
            continue
        llm_call_count += 1
        usage = message.usage_metadata or {}
        input_tokens += int(usage.get("input_tokens", 0) or 0)
        output_tokens += int(usage.get("output_tokens", 0) or 0)
        total_tokens += int(usage.get("total_tokens", 0) or 0)

    tools_used = state.get("tools_used", [])
    resolved_tools_used = tools_used if isinstance(tools_used, list) else []
    tool_execution_count = int(state.get("tool_execution_count", 0) or 0)
    return _build_turn_observability(
        latency_ms=latency_ms,
        llm_call_count=llm_call_count,
        tool_call_count=tool_execution_count,
        tools_used=cast(list[str], resolved_tools_used),
        token_usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
    )


def elapsed_latency_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def build_debug_info_from_state(
    state: AnalyticsGraphState,
    *,
    latency_ms: int | None = None,
) -> DebugInfo | None:
    raw_errors = state.get("debug_errors", [])
    errors: list[DebugError] = []

    for raw_error in raw_errors:
        try:
            errors.append(DebugError.model_validate(raw_error))
        except ValidationError:
            continue

    resolved_question = state.get("resolved_question") or None

    router_intent: str | None = None
    router_short_circuit: str | None = None
    raw_router = state.get("router_decision")
    if raw_router:
        try:
            rd = RouterDecision.model_validate(raw_router)
            router_intent = rd.intent
            if rd.refusal_reason:
                router_short_circuit = f"refusal:{rd.refusal_reason}"
            elif rd.clarification_reason:
                router_short_circuit = f"clarification:{rd.clarification_reason}"
        except Exception:
            pass

    agent_tool_calls = _extract_agent_tool_calls(state)

    observability = _extract_turn_observability_from_state(
        state,
        latency_ms=latency_ms,
    )

    return DebugInfo(
        resolved_question=resolved_question,
        router_intent=router_intent,
        router_short_circuit=router_short_circuit,
        agent_tool_calls=agent_tool_calls,
        errors=errors,
        observability=observability,
    )


def build_timeout_debug_info(
    request: QueryRequest,
    exc: LlmTimeoutError,
    *,
    latency_ms: int | None = None,
) -> DebugInfo:
    return DebugInfo(
        resolved_question=request.question,
        errors=[
            DebugError(
                source="api",
                message=exc.debug_message,
                error_type=exc.error_type or type(exc).__name__,
            )
        ],
        observability=_build_turn_observability(
            latency_ms=latency_ms,
            llm_call_count=0,
            tool_call_count=0,
            tools_used=[],
        ),
    )


def build_tool_execution_debug_info(
    request: QueryRequest,
    exc: ToolExecutionError,
    *,
    latency_ms: int | None = None,
) -> DebugInfo:
    tools_used = [exc.tool_name] if exc.tool_name else []
    return DebugInfo(
        resolved_question=exc.resolved_question or request.question,
        errors=[
            DebugError(
                source="tool_executor",
                message=exc.debug_message,
                error_type=exc.error_type or type(exc).__name__,
                tool_name=exc.tool_name,
            )
        ],
        observability=_build_turn_observability(
            latency_ms=latency_ms,
            llm_call_count=0,
            tool_call_count=len(tools_used),
            tools_used=tools_used,
        ),
    )


def build_error_response(
    detail: str,
    *,
    debug: DebugInfo | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=detail, debug=debug).model_dump(mode="json"),
    )


def build_query_metadata(
    *,
    thread_id: str,
    request_thread_id: str | None,
    context_message_count: int,
    debug_info: DebugInfo | None = None,
) -> QueryMetadata:
    return QueryMetadata(
        thread_id=thread_id,
        thread_id_source="provided" if request_thread_id else "generated",
        context_message_count=context_message_count,
        debug=debug_info,
    )
