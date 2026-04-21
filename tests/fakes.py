from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from app.graph.workflow import build_analytics_graph
from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _extract_section(content: str, start: str, end: str | None = None) -> str:
    if start not in content:
        return content.strip()

    section = content.split(start, maxsplit=1)[1]
    if end is not None and end in section:
        section = section.split(end, maxsplit=1)[0]
    return section.strip()


@dataclass(frozen=True)
class RecordedToolCall:
    tool_name: str
    start_date: date
    end_date: date
    traffic_source: str | None


@dataclass
class FakeAnalyticsTools:
    calls: list[RecordedToolCall] = field(default_factory=list)

    def build(self) -> tuple[BaseTool, ...]:
        def run_traffic_volume(
            start_date: date,
            end_date: date,
            traffic_source: str | None = None,
        ) -> dict[str, Any]:
            self.calls.append(
                RecordedToolCall(
                    tool_name="traffic_volume_analyzer",
                    start_date=start_date,
                    end_date=end_date,
                    traffic_source=traffic_source,
                )
            )
            return {
                "traffic_source": traffic_source,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "rows": [
                    {
                        "traffic_source": traffic_source or "Search",
                        "user_count": 42,
                    }
                ],
            }

        def run_channel_performance(
            start_date: date,
            end_date: date,
            traffic_source: str | None = None,
        ) -> dict[str, Any]:
            self.calls.append(
                RecordedToolCall(
                    tool_name="channel_performance_analyzer",
                    start_date=start_date,
                    end_date=end_date,
                    traffic_source=traffic_source,
                )
            )
            return {
                "traffic_source": traffic_source,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "rows": [
                    {
                        "traffic_source": traffic_source or "Search",
                        "total_orders": 7,
                        "total_revenue": "1234.56",
                    }
                ],
            }

        return (
            StructuredTool.from_function(
                func=run_traffic_volume,
                name="traffic_volume_analyzer",
                description="Fake traffic volume analyzer for deterministic tests.",
                args_schema=TrafficVolumeInput,
            ),
            StructuredTool.from_function(
                func=run_channel_performance,
                name="channel_performance_analyzer",
                description="Fake channel performance analyzer for deterministic tests.",
                args_schema=ChannelPerformanceInput,
            ),
        )


@dataclass
class FakeAgentLLM:
    """Simulates LLM-driven tool calling for deterministic graph tests.

    First call per turn: emits an AIMessage with tool_calls based on the
    question content (simulating the LLM deciding which tool to use).
    Subsequent calls in the same turn (after tool results arrive): emits
    a plain AIMessage with the synthesized answer text.
    """

    prompts: list[str] = field(default_factory=list)
    _calls_in_session: int = field(default=0, init=False, repr=False)

    def _pick_tool_name(self, question_text: str) -> str:
        q = question_text.lower()
        if any(
            kw in q
            for kw in ("receita", "pedido", "revenue", "performance", "melhor", "ranking")
        ):
            return "channel_performance_analyzer"
        return "traffic_volume_analyzer"

    def _pick_traffic_source(self, question_text: str) -> str | None:
        q = question_text.lower()
        channel_map = {
            "search": "Search",
            "organic": "Organic",
            "facebook": "Facebook",
            "instagram": "Instagram",
        }
        for token, canonical in channel_map.items():
            if token in q:
                return canonical
        return None

    def _has_follow_up_context(self, messages: list[Any]) -> bool:
        return any(
            isinstance(message, SystemMessage)
            and "Contexto analitico anterior do mesmo thread:" in _extract_text(message.content)
            for message in messages
        )

    def _has_ambiguous_analytics_guidance(self, messages: list[Any]) -> bool:
        return any(
            isinstance(message, SystemMessage)
            and "a pergunta esta no dominio, mas ainda esta ambigua entre volume de usuarios e performance financeira" in _extract_text(message.content)
            for message in messages
        )

    def _build_follow_up_answer(self, messages: list[Any]) -> AIMessage:
        question = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                question = _extract_text(message.content)
                if question:
                    break
        return AIMessage(content=f"FOLLOW_UP::{question}")

    def _build_ambiguous_metric_clarification(self, messages: list[Any]) -> AIMessage:
        question = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                question = _extract_text(message.content)
                if question:
                    break

        traffic_source = self._pick_traffic_source(question)
        channel_label = traffic_source or "os canais"
        return AIMessage(
            content=(
                f"Entendi a pergunta sobre {channel_label}, mas preciso alinhar o foco antes. "
                "Voce quer ver volume de usuarios ou performance financeira "
                "(receita e pedidos)?"
            )
        )

    def _has_tool_message(self, messages: list[Any]) -> bool:
        from langchain_core.messages import ToolMessage

        return any(isinstance(m, ToolMessage) for m in messages)

    def invoke(self, messages: list[Any]) -> AIMessage:
        self._calls_in_session += 1
        last_content = _extract_text(messages[-1].content) if messages else ""
        self.prompts.append(last_content)

        # If there's already a ToolMessage in the conversation, the LLM is
        # being called after tool execution — produce the final answer.
        if self._has_tool_message(messages):
            # Find the tool name from the ToolMessage.
            from langchain_core.messages import ToolMessage

            tool_name = "unknown"
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and msg.name:
                    tool_name = msg.name
                    break
            # Find the original human question.
            question = ""
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    question = _extract_text(msg.content)
                    break
            return AIMessage(content=f"SYNTH::{tool_name}::{question}")

        if self._has_follow_up_context(messages):
            return self._build_follow_up_answer(messages)

        if self._has_ambiguous_analytics_guidance(messages):
            return self._build_ambiguous_metric_clarification(messages)

        all_human_text = " ".join(
            _extract_text(msg.content)
            for msg in messages
            if isinstance(msg, HumanMessage)
        )
        tool_name = self._pick_tool_name(all_human_text)
        traffic_source = self._pick_traffic_source(all_human_text)
        # Build a minimal tool_call that ToolNode can execute.
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": tool_name,
                    "args": {
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-31",
                        "traffic_source": traffic_source,
                    },
                    "id": str(uuid4()),
                    "type": "tool_call",
                }
            ],
        )


@dataclass
class FakeSynthesisLLM:
    """Plain LLM fake used by the insight_synthesizer (follow-ups only)."""

    prompts: list[str] = field(default_factory=list)

    def invoke(self, messages: list[Any]) -> AIMessage:
        prompt = _extract_text(messages[-1].content)
        self.prompts.append(prompt)

        if "Pergunta de follow-up:" in prompt:
            question = _extract_section(
                prompt,
                "Pergunta de follow-up:\n",
                "\n\nContexto analitico anterior:\n",
            )
            return AIMessage(content=f"FOLLOW_UP::{question}")

        question = _extract_section(
            prompt,
            "Pergunta original:\n",
            "\n\nResultados estruturados:\n",
        )
        if "Tool: traffic_volume_analyzer" in prompt:
            tool_name = "traffic_volume_analyzer"
        elif "Tool: channel_performance_analyzer" in prompt:
            tool_name = "channel_performance_analyzer"
        else:
            tool_name = "unknown"
        return AIMessage(content=f"SYNTH::{tool_name}::{question}")


@dataclass
class DeterministicGraphBundle:
    graph: Any
    agent_llm: FakeAgentLLM
    synthesis_llm: FakeSynthesisLLM
    tools: FakeAnalyticsTools


def build_deterministic_graph_bundle() -> DeterministicGraphBundle:
    fake_agent_llm = FakeAgentLLM()
    fake_synthesis_llm = FakeSynthesisLLM()
    fake_tools = FakeAnalyticsTools()
    graph = build_analytics_graph(
        agent_llm=fake_agent_llm,
        response_llm=fake_synthesis_llm,
        tools=fake_tools.build(),
        checkpointer=MemorySaver(),
    )
    return DeterministicGraphBundle(
        graph=graph,
        agent_llm=fake_agent_llm,
        synthesis_llm=fake_synthesis_llm,
        tools=fake_tools,
    )
