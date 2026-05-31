from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
import inspect
from typing import Any, Literal, cast

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langchain_core.runnables import RunnableLambda

from app.agent.messages import (
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    TEMPORARY_LLM_FAILURE_MESSAGE,
    TEMPORARY_TOOL_FAILURE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    content_to_text,
    get_current_turn_messages,
)
from app.agent.nodes import (
    build_agent_nodes,
    build_preprocess_node,
    build_tool_executor_node,
)
from app.agent.prompts import build_conversation_system_prompt
from app.agent.state import AnalyticsGraphState, ToolExecutionError
from app.graph.tools import get_analytics_tools
from app.infra.config import Settings
from app.infra.env import get_settings
from app.infra.llm import build_tool_enabled_llm

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

    preprocess_node = build_preprocess_node(settings, router_llm)
    agent_node, agent_node_async = build_agent_nodes(resolved_agent_llm, agent_system_prompt)
    tool_executor_node = build_tool_executor_node(tools_by_name)

    graph = StateGraph(AnalyticsGraphState)
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("agent", RunnableLambda(agent_node, afunc=agent_node_async, name="agent"))
    graph.add_node("tool_executor", tool_executor_node)

    graph.add_edge(START, "preprocess")
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
