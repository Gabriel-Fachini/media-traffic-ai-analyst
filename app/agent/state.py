from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


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
