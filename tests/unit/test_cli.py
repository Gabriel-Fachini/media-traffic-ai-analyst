from __future__ import annotations

from app.cli import _format_debug_info, _iter_sse_events, _resolve_stream_api_url
from app.schemas import DebugInfo, TokenUsage, TurnObservability


def test_cli_resolves_stream_url_from_query_endpoint() -> None:
    assert (
        _resolve_stream_api_url("http://127.0.0.1:8000/query")
        == "http://127.0.0.1:8000/query/stream"
    )
    assert (
        _resolve_stream_api_url("http://127.0.0.1:8000/query/stream")
        == "http://127.0.0.1:8000/query/stream"
    )


def test_cli_parses_sse_blocks_into_event_payloads() -> None:
    lines = [
        "event: metadata",
        'data: {"thread_id":"session-123"}',
        "",
        "event: token",
        'data: {"text":"Resposta parcial"}',
        "",
    ]

    events = list(_iter_sse_events(lines))

    assert events == [
        ("metadata", {"thread_id": "session-123"}),
        ("token", {"text": "Resposta parcial"}),
    ]


def test_cli_debug_formatter_includes_observability_summary() -> None:
    message = _format_debug_info(
        DebugInfo(
            observability=TurnObservability(
                latency_ms=123,
                llm_call_count=2,
                tool_call_count=1,
                tools_used=["traffic_volume_analyzer"],
                token_usage=TokenUsage(
                    input_tokens=50,
                    output_tokens=32,
                    total_tokens=82,
                ),
            )
        )
    )

    assert "latency_ms: 123" in message
    assert "llm_call_count: 2" in message
    assert "tool_call_count: 1" in message
    assert "tools_used: traffic_volume_analyzer" in message
    assert "token_usage: input=50 output=32 total=82" in message
