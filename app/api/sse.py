from __future__ import annotations

import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command

from app.agent.graph import AnalyticsGraphState, ToolExecutionError, astream_analytics_graph_events
from app.agent.messages import content_to_text
from app.api.observability import (
    build_debug_info_from_state,
    build_query_metadata,
    build_timeout_debug_info,
    build_tool_execution_debug_info,
    elapsed_latency_ms,
)
from app.api.schemas import ErrorResponse, QueryRequest
from app.api.deps import LLM_TIMEOUT_ERROR_MESSAGE
from app.agent.messages import TEMPORARY_TOOL_FAILURE_MESSAGE
from app.infra.llm import LlmTimeoutError


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def extract_router_sse_payload(raw_event: dict[str, Any]) -> dict[str, Any] | None:
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

    return {
        "intent": router_decision.get("intent"),
        "resolved_question": update.get("resolved_question"),
        "needs_clarification": router_decision.get("needs_clarification", False),
        "clarification_reason": router_decision.get("clarification_reason"),
        "refusal_reason": router_decision.get("refusal_reason"),
    }


def extract_agent_token_sse_payload(raw_event: dict[str, Any]) -> dict[str, Any] | None:
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


def extract_final_state(raw_event: dict[str, Any]) -> AnalyticsGraphState | None:
    from typing import cast
    if raw_event.get("event") != "on_chain_end" or raw_event.get("name") != "LangGraph":
        return None
    output = raw_event.get("data", {}).get("output")
    return cast(AnalyticsGraphState, output) if isinstance(output, dict) else None


async def stream_query_events(
    request: QueryRequest,
    graph: object,
    *,
    thread_id: str,
    debug: bool,
) -> AsyncIterator[str]:
    started_at = perf_counter()
    yield format_sse_event(
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
            router_payload = extract_router_sse_payload(raw_event)
            if router_payload is not None:
                yield format_sse_event("router", router_payload)

            if raw_event.get("event") == "on_tool_start":
                yield format_sse_event(
                    "tool_start",
                    {
                        "tool_name": raw_event.get("name"),
                        "args": raw_event.get("data", {}).get("input", {}),
                    },
                )
                continue

            if raw_event.get("event") == "on_tool_end":
                yield format_sse_event(
                    "tool_end",
                    {
                        "tool_name": raw_event.get("name"),
                        "output": raw_event.get("data", {}).get("output"),
                    },
                )
                continue

            token_payload = extract_agent_token_sse_payload(raw_event)
            if token_payload is not None:
                yield format_sse_event("token", token_payload)

            final_state = extract_final_state(raw_event)
            if final_state is not None:
                messages = final_state.get("messages", [])
                debug_info = (
                    build_debug_info_from_state(
                        final_state,
                        latency_ms=elapsed_latency_ms(started_at),
                    )
                    if debug
                    else None
                )
                metadata = build_query_metadata(
                    thread_id=thread_id,
                    request_thread_id=request.thread_id,
                    context_message_count=len(messages),
                    debug_info=debug_info,
                )
                yield format_sse_event(
                    "final",
                    {
                        "answer": final_state.get("final_answer", ""),
                        "tools_used": final_state.get("tools_used", []),
                        "metadata": metadata.model_dump(mode="json"),
                    },
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
        yield format_sse_event(
            "error",
            ErrorResponse(
                detail=LLM_TIMEOUT_ERROR_MESSAGE,
                debug=debug_info,
            ).model_dump(mode="json"),
        )
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
        yield format_sse_event(
            "error",
            ErrorResponse(
                detail=TEMPORARY_TOOL_FAILURE_MESSAGE,
                debug=debug_info,
            ).model_dump(mode="json"),
        )
