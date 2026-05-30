from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from app.graph.date_normalizer import normalize_text as _normalize_text
from tests.deterministic_router import build_router_decision
from app.graph.workflow import build_analytics_graph
from app.schemas.router import RouterDecision
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

    def _get_router_guidance(self, messages: list[Any]) -> dict[str, str | None]:
        """Extract intent and traffic_source from the router guidance SystemMessage."""
        for msg in messages:
            if not isinstance(msg, SystemMessage):
                continue
            content = _extract_text(msg.content)
            if "Contexto estruturado do router" not in content:
                continue
            result: dict[str, str | None] = {}
            for line in content.split("\n"):
                if "- intent: " in line:
                    result["intent"] = line.split("- intent: ")[-1].strip()
                elif "- traffic_source: " in line:
                    src = line.split("- traffic_source: ")[-1].strip()
                    result["traffic_source"] = None if "agregado" in src else src
            return result
        return {}

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


_DIAGNOSTIC_WORDS: frozenset[str] = frozenset(
    {"explica", "explicar", "causa", "hipotese", "diagnostico", "motivo"}
)
_STRATEGY_WORDS: frozenset[str] = frozenset(
    {"acao", "acoes", "priorizar", "recomend", "sugest", "plano", "melhorar", "fortalecer"}
)
_GENERIC_FOLLOW_UP_WORDS: frozenset[str] = frozenset(
    {"ajude", "ajudar", "continue", "continuar", "segue", "seguir", "siga"}
)


@dataclass
class FakeRouterRunnable:
    """Simulates the chain returned by base_llm.with_structured_output(RouterDecision).

    Replicates the thread-aware behavior of the real LLM router:
    1. If the base decision is complete (no clarification, no refusal), return it.
    2. If there is a prior successful ToolMessage and the question has direct
       diagnostic/strategy language, return the matching follow-up intent.
    3. If there is a prior ToolMessage and the question has generic "help me" language,
       infer the follow-up type from the most recent AI message.
    4. If the base decision has no specific traffic_source and there is a prior
       HumanMessage, try combining questions (simulates LLM date/metric inference).
    5. Fall back to the raw base decision.
    """

    def invoke(self, messages: list[Any]) -> RouterDecision:
        question = ""
        prev_human_question = ""
        found_current = False
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = _extract_text(msg.content)
                if not found_current:
                    question = content
                    found_current = True
                elif content and content != question and not prev_human_question:
                    prev_human_question = content

        base_decision = build_router_decision(question)

        # Complete decision — return without further inspection.
        if not base_decision.needs_clarification and base_decision.refusal_reason is None:
            return base_decision

        # Prior tool result → follow-up intent detection.
        if any(isinstance(m, ToolMessage) for m in messages):
            normalized_q = _normalize_text(question)
            if any(w in normalized_q for w in _DIAGNOSTIC_WORDS) or bool(
                re.search(r"por que|porque", normalized_q)
            ):
                return RouterDecision(
                    intent="diagnostic_follow_up",
                )
            if any(w in normalized_q for w in _STRATEGY_WORDS):
                return RouterDecision(
                    intent="strategy_follow_up",
                )
            # Generic "help me" phrase — infer intent from most recent AI text.
            if any(w in normalized_q for w in _GENERIC_FOLLOW_UP_WORDS):
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and not msg.tool_calls:
                        prior_text = _normalize_text(_extract_text(msg.content))
                        if any(w in prior_text for w in _DIAGNOSTIC_WORDS) or bool(
                            re.search(r"por que|porque|explica", prior_text)
                        ):
                            return RouterDecision(
                                intent="diagnostic_follow_up",
                            )
                        return RouterDecision(
                            intent="strategy_follow_up",
                        )

        # Merge with previous HumanMessage only when base has no specific traffic_source.
        # A channel-specific query (traffic_source set) is treated as a fresh question.
        if prev_human_question and base_decision.normalized_params.traffic_source is None:
            combined = f"{prev_human_question.rstrip()} {question.strip()}".strip()
            combined_decision = build_router_decision(combined)
            if (
                not combined_decision.needs_clarification
                and combined_decision.refusal_reason is None
            ):
                return combined_decision

        return base_decision


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
        router_llm=FakeRouterRunnable(),
        tools=fake_tools.build(),
        checkpointer=MemorySaver(),
    )
    return DeterministicGraphBundle(
        graph=graph,
        agent_llm=fake_agent_llm,
        synthesis_llm=fake_synthesis_llm,
        tools=fake_tools,
    )
