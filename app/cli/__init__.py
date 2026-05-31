"""CLI delivery layer — Typer app, SSE client, Rich rendering."""
from __future__ import annotations

from app.cli.app import entrypoint as entrypoint
from app.cli.rendering import _format_debug_info as _format_debug_info
from app.cli.sse_client import _iter_sse_events as _iter_sse_events
from app.cli.sse_client import _resolve_stream_api_url as _resolve_stream_api_url

__all__ = [
    "entrypoint",
    "_format_debug_info",
    "_iter_sse_events",
    "_resolve_stream_api_url",
]
