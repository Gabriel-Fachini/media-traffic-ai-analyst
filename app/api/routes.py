from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent.graph import ToolExecutionError, invoke_analytics_graph
from app.api.deps import (
    LLM_TIMEOUT_ERROR_MESSAGE,
    AnalyticsGraphDep,
    DebugHeader,
    HealthResponse,
    QueryRequestBody,
    SettingsDep,
)
from app.api.observability import (
    build_debug_info_from_state,
    build_error_response,
    build_query_metadata,
    build_timeout_debug_info,
    build_tool_execution_debug_info,
    elapsed_latency_ms,
)
from app.api.schemas import ErrorResponse, QueryResponse
from app.agent.messages import TEMPORARY_TOOL_FAILURE_MESSAGE
from app.api.sse import stream_query_events
from app.infra.llm import LlmTimeoutError

app = FastAPI(title="Media Traffic AI Analyst")


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check(settings: SettingsDep) -> HealthResponse:
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
            build_timeout_debug_info(
                request,
                exc,
                latency_ms=elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        return build_error_response(LLM_TIMEOUT_ERROR_MESSAGE, debug=debug_info)
    except ToolExecutionError as exc:
        debug_info = (
            build_tool_execution_debug_info(
                request,
                exc,
                latency_ms=elapsed_latency_ms(started_at),
            )
            if debug
            else None
        )
        return build_error_response(TEMPORARY_TOOL_FAILURE_MESSAGE, debug=debug_info)

    messages = state.get("messages", [])
    debug_info = (
        build_debug_info_from_state(
            state,
            latency_ms=elapsed_latency_ms(started_at),
        )
        if debug
        else None
    )

    return QueryResponse(
        answer=state.get("final_answer", ""),
        tools_used=state.get("tools_used", []),
        metadata=build_query_metadata(
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
    thread_id = request.thread_id or str(uuid4())
    return StreamingResponse(
        stream_query_events(
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
