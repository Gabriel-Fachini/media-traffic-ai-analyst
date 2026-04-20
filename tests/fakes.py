from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage
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
class FakeSynthesisLLM:
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
    llm: FakeSynthesisLLM
    tools: FakeAnalyticsTools


def build_deterministic_graph_bundle() -> DeterministicGraphBundle:
    fake_llm = FakeSynthesisLLM()
    fake_tools = FakeAnalyticsTools()
    graph = build_analytics_graph(
        response_llm=fake_llm,
        tools=fake_tools.build(),
        checkpointer=MemorySaver(),
    )
    return DeterministicGraphBundle(graph=graph, llm=fake_llm, tools=fake_tools)
