from __future__ import annotations

import json
from collections.abc import AsyncIterator
from functools import lru_cache
from time import perf_counter
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command
from pydantic import BaseModel, ValidationError

from app.graph import (
    AnalyticsGraphState,
    astream_analytics_graph_events,
    invoke_analytics_graph,
)
from app.infra.llm import LlmTimeoutError
from app.graph.workflow import (
    TEMPORARY_TOOL_FAILURE_MESSAGE,
    ToolExecutionError,
    content_to_text,
    get_current_turn_messages,
    get_persistent_analytics_graph,
)
from app.schemas import (
    AgentToolCall,
    DebugError,
    DebugInfo,
    ErrorResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
    TokenUsage,
    TurnObservability,
)
from app.schemas.router import RouterDecision
from app.infra.config import Settings
from app.infra.env import get_settings

app = FastAPI(title="Media Traffic AI Analyst")

LLM_TIMEOUT_ERROR_MESSAGE = (
    "Nao consegui concluir a analise agora porque o provedor de IA excedeu o "
    "tempo limite. Tente novamente em instantes."
)

SettingsDep = Annotated[Settings, Depends(get_settings)]
QueryRequestBody = Annotated[
    QueryRequest,
    Body(
        description=(
            "Pergunta do usuario final sobre trafego, pedidos ou receita por canal."
        )
    ),
]


class HealthResponse(BaseModel):
    status: str
    environment: str


@lru_cache
def get_query_graph() -> object:
    """Return the cached analytics graph used by HTTP request handlers.

    The API layer depends on a persistent graph instance so repeated requests
    that reuse the same `thread_id` can recover conversation context from the
    checkpointer.
    """
    return get_persistent_analytics_graph()


AnalyticsGraphDep = Annotated[object, Depends(get_query_graph)]
DebugHeader = Annotated[
    bool,
    Header(
        alias="X-Debug",
        description="Quando verdadeiro, inclui detalhes diagnosticos opcionais na resposta.",
    ),
]


def _extract_agent_tool_calls(state: AnalyticsGraphState) -> list[AgentToolCall]:
    """Extract all tool_calls emitted by the LLM agent in the current state."""
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
    tools_used: list[str],
    token_usage: TokenUsage | None = None,
) -> TurnObservability:
    """Build the public observability summary for one turn."""
    return TurnObservability(
        latency_ms=latency_ms,
        llm_call_count=llm_call_count,
        tool_call_count=len(tools_used),
        tools_used=tools_used,
        token_usage=token_usage or TokenUsage(),
    )


def _extract_turn_observability_from_state(
    state: AnalyticsGraphState,
    *,
    latency_ms: int | None,
) -> TurnObservability:
    """Aggregate latency, token usage, and tool usage from the current turn state."""
    current_turn_messages = get_current_turn_messages(state)
    llm_call_count = 0
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
    return _build_turn_observability(
        latency_ms=latency_ms,
        llm_call_count=llm_call_count,
        tools_used=cast(list[str], resolved_tools_used),
        token_usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
    )


def _elapsed_latency_ms(started_at: float) -> int:
    """Convert a `perf_counter()` start timestamp into elapsed milliseconds."""
    return max(0, round((perf_counter() - started_at) * 1000))


def _build_debug_info_from_state(
    state: AnalyticsGraphState,
    *,
    latency_ms: int | None = None,
) -> DebugInfo | None:
    """Translate graph state into the optional public debug payload.

    The workflow stores low-level execution details in plain dictionaries and
    messages. This helper extracts only the diagnostics that are safe and useful
    for API consumers: resolved question, router signals, tool calls, and
    structured technical errors.
    """
    raw_errors = state.get("debug_errors", [])
    errors: list[DebugError] = []

    for raw_error in raw_errors:
        try:
            errors.append(DebugError.model_validate(raw_error))
        except ValidationError:
            continue

    resolved_question = state.get("resolved_question") or None

    # Extract only routing signals from router_decision (not tool args).
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


def _build_timeout_debug_info(
    request: QueryRequest,
    exc: LlmTimeoutError,
    *,
    latency_ms: int | None = None,
) -> DebugInfo:
    """Build a debug payload for LLM timeout failures exposed by the API."""
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
            tools_used=[],
        ),
    )


def _build_tool_execution_debug_info(
    request: QueryRequest,
    exc: ToolExecutionError,
    *,
    latency_ms: int | None = None,
) -> DebugInfo:
    """Build a debug payload for tool execution failures exposed by the API."""
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
            tools_used=tools_used,
        ),
    )


def _build_error_response(
    detail: str,
    *,
    debug: DebugInfo | None = None,
) -> JSONResponse:
    """Return the standardized HTTP 500 payload used by `/query`."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=detail, debug=debug).model_dump(mode="json"),
    )


def _build_query_metadata(
    *,
    thread_id: str,
    request_thread_id: str | None,
    context_message_count: int,
    debug_info: DebugInfo | None = None,
) -> QueryMetadata:
    """Assemble the shared metadata contract returned by sync and SSE endpoints."""
    return QueryMetadata(
        thread_id=thread_id,
        thread_id_source="provided" if request_thread_id else "generated",
        context_message_count=context_message_count,
        debug=debug_info,
    )


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    """Serialize one SSE event block using the `event:` + `data:` wire format."""
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _extract_router_sse_payload(raw_event: dict[str, Any]) -> dict[str, Any] | None:
    """Project LangGraph preprocess events into the public `router` SSE payload.

    Only preprocess `on_chain_stream` events contain the router `Command` update
    with the normalized question and structured router decision for the current
    turn. All other raw events are ignored here.
    """
    if raw_event.get("event") != "on_chain_stream" or raw_event.get("name") != "preprocess":
        return None

    chunk = raw_event.get("data", {}).get("chunk")
    if not isinstance(chunk, Command):
        return None

    update = getattr(chunk, "update", None)
    if not isinstance(update, dict):
        return None

    router_decision = update.get("router_decision")
    if not isinstance(router_decision, dict):
        return None

    payload: dict[str, Any] = {
        "intent": router_decision.get("intent"),
        "resolved_question": update.get("resolved_question"),
        "needs_clarification": router_decision.get("needs_clarification", False),
        "clarification_reason": router_decision.get("clarification_reason"),
        "refusal_reason": router_decision.get("refusal_reason"),
    }
    return payload


def _extract_agent_token_sse_payload(raw_event: dict[str, Any]) -> dict[str, Any] | None:
    """Project agent node stream events into public text chunks.

    Prefer provider/model chunk events when available because they arrive in
    real time. The older agent-node snapshot format remains as a fallback for
    non-streaming fakes used in tests.
    """
    event_name = raw_event.get("event")
    metadata = raw_event.get("metadata", {})
    if isinstance(metadata, dict):
        langgraph_node = metadata.get("langgraph_node")
        if langgraph_node is not None and langgraph_node != "agent":
            return None

    if event_name in {"on_chat_model_stream", "on_llm_stream"}:
        chunk = raw_event.get("data", {}).get("chunk")
        if isinstance(chunk, AIMessageChunk):
            if chunk.tool_call_chunks or chunk.tool_calls:
                return None
            text_delta = content_to_text(chunk.content)
            if text_delta.strip():
                return {"text_delta": text_delta}
        return None

    if event_name != "on_chain_stream" or raw_event.get("name") != "agent":
        return None

    chunk = raw_event.get("data", {}).get("chunk")
    if not isinstance(chunk, Command):
        return None

    update = getattr(chunk, "update", None)
    if not isinstance(update, dict):
        return None

    messages = update.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or last_message.tool_calls:
        return None

    content = content_to_text(last_message.content).strip()
    if not content:
        return None

    return {"text": content}


def _extract_final_state(raw_event: dict[str, Any]) -> AnalyticsGraphState | None:
    """Return the final graph state once the top-level LangGraph run finishes."""
    if raw_event.get("event") != "on_chain_end" or raw_event.get("name") != "LangGraph":
        return None

    output = raw_event.get("data", {}).get("output")
    return cast(AnalyticsGraphState, output) if isinstance(output, dict) else None


async def _stream_query_events(
    request: QueryRequest,
    graph: object,
    *,
    thread_id: str,
    debug: bool,
) -> AsyncIterator[str]:
    """Adapt internal LangGraph events into the public SSE protocol.

    The raw framework events are intentionally not exposed directly. This
    adapter emits a stable sequence of API-level events (`metadata`, `router`,
    `tool_start`, `tool_end`, `token`, `final`, `error`) that clients can rely
    on without depending on LangGraph's internal event schema.
    """
    started_at = perf_counter()
    yield _format_sse_event(
        "metadata",
        {
            "thread_id": thread_id,
            "thread_id_source": "provided" if request.thread_id else "generated",
        },
    )

    try:
        async for raw_event in astream_analytics_graph_events(
            request.question,
            thread_id=thread_id,
            graph=graph,
            version="v2",
        ):
            router_payload = _extract_router_sse_payload(raw_event)
            if router_payload is not None:
                yield _format_sse_event("router", router_payload)

            if raw_event.get("event") == "on_tool_start":
                yield _format_sse_event(
                    "tool_start",
                    {
                        "tool_name": raw_event.get("name"),
                        "args": raw_event.get("data", {}).get("input", {}),
                    },
                )
                continue

            if raw_event.get("event") == "on_tool_end":
                yield _format_sse_event(
                    "tool_end",
                    {
                        "tool_name": raw_event.get("name"),
                        "output": raw_event.get("data", {}).get("output"),
                    },
                )
                continue

            token_payload = _extract_agent_token_sse_payload(raw_event)
            if token_payload is not None:
                yield _format_sse_event("token", token_payload)

            final_state = _extract_final_state(raw_event)
            if final_state is not None:
                messages = final_state.get("messages", [])
                debug_info = (
                    _build_debug_info_from_state(
                        final_state,
                        latency_ms=_elapsed_latency_ms(started_at),
                    )
                    if debug
                    else None
                )
                metadata = _build_query_metadata(
                    thread_id=thread_id,
                    request_thread_id=request.thread_id,
                    context_message_count=len(messages),
                    debug_info=debug_info,
                )
                yield _format_sse_event(
                    "final",
                    {
                        "answer": final_state.get("final_answer", ""),
                        "tools_used": final_state.get("tools_used", []),
                        "metadata": metadata.model_dump(mode="json"),
                    },
                )
    except LlmTimeoutError as exc:
        debug_info = (
            _build_timeout_debug_info(
                request,
                exc,
                latency_ms=_elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        yield _format_sse_event(
            "error",
            ErrorResponse(
                detail=LLM_TIMEOUT_ERROR_MESSAGE,
                debug=debug_info,
            ).model_dump(mode="json"),
        )
    except ToolExecutionError as exc:
        debug_info = (
            _build_tool_execution_debug_info(
                request,
                exc,
                latency_ms=_elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        yield _format_sse_event(
            "error",
            ErrorResponse(
                detail=TEMPORARY_TOOL_FAILURE_MESSAGE,
                debug=debug_info,
            ).model_dump(mode="json"),
        )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check(settings: SettingsDep) -> HealthResponse:
    """Return a lightweight readiness payload for the local API process."""
    return HealthResponse(status="ok", environment=settings.app_env)


@app.post(
    "/query",
    response_model=QueryResponse,
    tags=["query"],
    summary="Recebe uma pergunta de analytics e retorna a resposta do agente",
    responses={
        500: {
            "model": ErrorResponse,
            "description": "Falha temporaria ao consultar dados ou sintetizar via LLM.",
        }
    },
)
def query_analytics(
    request: QueryRequestBody,
    graph: AnalyticsGraphDep,
    debug: DebugHeader = False,
) -> QueryResponse | JSONResponse:
    """Execute one analytics turn synchronously and return the final answer."""
    thread_id = request.thread_id or str(uuid4())
    started_at = perf_counter()
    try:
        state = invoke_analytics_graph(
            request.question,
            thread_id=thread_id,
            graph=graph,
        )
    except LlmTimeoutError as exc:
        debug_info = (
            _build_timeout_debug_info(
                request,
                exc,
                latency_ms=_elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        return _build_error_response(LLM_TIMEOUT_ERROR_MESSAGE, debug=debug_info)
    except ToolExecutionError as exc:
        debug_info = (
            _build_tool_execution_debug_info(
                request,
                exc,
                latency_ms=_elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        return _build_error_response(TEMPORARY_TOOL_FAILURE_MESSAGE, debug=debug_info)

    messages = state.get("messages", [])
    debug_info = (
        _build_debug_info_from_state(
            state,
            latency_ms=_elapsed_latency_ms(started_at),
        )
        if debug
        else None
    )

    return QueryResponse(
        answer=state.get("final_answer", ""),
        tools_used=state.get("tools_used", []),
        metadata=_build_query_metadata(
            thread_id=thread_id,
            request_thread_id=request.thread_id,
            context_message_count=len(messages),
            debug_info=debug_info,
        ),
    )


@app.post(
    "/query/stream",
    tags=["query"],
    summary="Recebe uma pergunta de analytics e retorna um stream SSE do agente",
)
async def query_analytics_stream(
    request: QueryRequestBody,
    graph: AnalyticsGraphDep,
    debug: DebugHeader = False,
) -> StreamingResponse:
    """Execute one analytics turn and expose its progress as SSE events."""
    thread_id = request.thread_id or str(uuid4())
    return StreamingResponse(
        _stream_query_events(
            request,
            graph,
            thread_id=thread_id,
            debug=debug,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
