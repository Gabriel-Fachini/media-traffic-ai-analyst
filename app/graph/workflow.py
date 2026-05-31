"""Backward-compat shim — real implementation moved to app/agent/."""

from app.agent.graph import (
    AnalyticsGraphState,
    ToolExecutionError,
    astream_analytics_graph_events,
    build_analytics_graph,
    content_to_text,
    get_current_turn_messages,
    get_persistent_analytics_graph,
    invoke_analytics_graph,
)
from app.agent.messages import (
    EMPTY_QUESTION_MESSAGE,
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    TEMPORARY_LLM_FAILURE_MESSAGE,
    TEMPORARY_TOOL_FAILURE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
)
from app.core.router.date_resolution import apply_date_normalizer as _apply_date_normalizer

__all__ = [
    "AnalyticsGraphState",
    "EMPTY_QUESTION_MESSAGE",
    "INVALID_DATES_MESSAGE",
    "MISSING_DATES_MESSAGE",
    "OUT_OF_SCOPE_MESSAGE",
    "TEMPORARY_LLM_FAILURE_MESSAGE",
    "TEMPORARY_TOOL_FAILURE_MESSAGE",
    "ToolExecutionError",
    "UNSUPPORTED_DIMENSION_MESSAGE",
    "astream_analytics_graph_events",
    "build_analytics_graph",
    "content_to_text",
    "get_current_turn_messages",
    "get_persistent_analytics_graph",
    "invoke_analytics_graph",
    "_apply_date_normalizer",
]
