from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from app.graph.date_normalizer import (
    _extract_relative_date_range,
    _extract_valid_and_invalid_explicit_dates,
    _resolve_reference_date,
    normalize_text as _normalize_text,
)
from app.graph.workflow import (
    INVALID_DATES_MESSAGE,
    MISSING_DATES_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    UNSUPPORTED_DIMENSION_MESSAGE,
    build_analytics_graph,
)
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


def _fake_usage_metadata(
    input_tokens: int,
    output_tokens: int,
) -> dict[str, int]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


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
        return AIMessage(
            content=f"FOLLOW_UP::{question}",
            usage_metadata=_fake_usage_metadata(18, 12),
        )

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
            ),
            usage_metadata=_fake_usage_metadata(16, 20),
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
            return AIMessage(
                content=f"SYNTH::{tool_name}::{question}",
                usage_metadata=_fake_usage_metadata(28, 24),
            )

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
            usage_metadata=_fake_usage_metadata(22, 8),
        )

    async def astream(self, messages: list[Any]) -> Any:
        """Yield deterministic chunks so graph streaming paths are exercised in tests."""
        response = self.invoke(messages)

        if response.tool_calls:
            tool_call = response.tool_calls[0]
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": tool_call["name"],
                        "args": json.dumps(tool_call["args"], ensure_ascii=False),
                        "id": tool_call["id"],
                        "index": 0,
                        "type": "tool_call_chunk",
                    }
                ],
                usage_metadata=response.usage_metadata,
            )
            return

        response_text = _extract_text(response.content)
        midpoint = max(1, len(response_text) // 2)
        first_chunk = response_text[:midpoint]
        second_chunk = response_text[midpoint:]

        yield AIMessageChunk(content=first_chunk)
        if second_chunk:
            yield AIMessageChunk(
                content=second_chunk,
                usage_metadata=response.usage_metadata,
            )


@dataclass
class FakeSynthesisLLM:
    """Plain LLM fake for synthesis/follow-up paths (no tool calls)."""

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
            return AIMessage(
                content=f"FOLLOW_UP::{question}",
                usage_metadata=_fake_usage_metadata(18, 12),
            )

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
        return AIMessage(
            content=f"SYNTH::{tool_name}::{question}",
            usage_metadata=_fake_usage_metadata(28, 24),
        )


_FAKE_UNSUPPORTED_DIMENSION_TOKENS: frozenset[str] = frozenset(
    {"campanha", "campanhas", "campaign", "campaigns", "anuncio", "anuncios", "ad", "ads"}
)
_FAKE_SOURCE_MAP: dict[str, str] = {
    "search": "Search",
    "organic": "Organic",
    "facebook": "Facebook",
    "instagram": "Instagram",
}
_FAKE_PERFORMANCE_TOKENS: frozenset[str] = frozenset(
    {"receita", "pedido", "pedidos", "revenue", "performance", "melhor", "ranking", "faturamento"}
)
_FAKE_VOLUME_TOKENS: frozenset[str] = frozenset(
    {"usuario", "usuarios", "trafego", "traffic", "volume"}
)


def _fake_classify(question: str) -> RouterDecision:
    """Minimal deterministic classifier for test fakes — not production-accurate."""
    ref = _resolve_reference_date(None)
    valid_dates, invalid_dates = _extract_valid_and_invalid_explicit_dates(question)
    relative_range, invalid_relative = _extract_relative_date_range(question, reference_date=ref)

    tokens = set(re.findall(r"[a-z0-9_]+", _normalize_text(question)))
    traffic_source: str | None = next((v for k, v in _FAKE_SOURCE_MAP.items() if k in tokens), None)

    if _FAKE_UNSUPPORTED_DIMENSION_TOKENS & tokens:
        return RouterDecision(
            intent="out_of_scope",
            refusal_reason="unsupported_dimension",
            response_message=UNSUPPORTED_DIMENSION_MESSAGE,
        )

    start_date = end_date = None
    if len(valid_dates) >= 2:
        start_date, end_date = valid_dates[0], valid_dates[1]
        if start_date > end_date:
            invalid_dates = [*invalid_dates, "inverted"]
            start_date = end_date = None
    elif len(valid_dates) == 1:
        start_date = end_date = valid_dates[0]
    elif relative_range is not None:
        start_date, end_date = relative_range

    if invalid_dates or invalid_relative:
        return RouterDecision(
            intent="channel_performance",
            traffic_source=traffic_source,
            needs_clarification=True,
            clarification_reason="invalid_dates",
            response_message=INVALID_DATES_MESSAGE,
        )

    has_performance = bool(_FAKE_PERFORMANCE_TOKENS & tokens)
    has_volume = bool(_FAKE_VOLUME_TOKENS & tokens)

    # No analytics context at all — out_of_scope triggers merge in FakeRouterRunnable.
    if not has_performance and not has_volume and traffic_source is None:
        return RouterDecision(
            intent="out_of_scope",
            refusal_reason="out_of_scope",
            response_message=OUT_OF_SCOPE_MESSAGE,
        )

    if has_performance:
        intent = "channel_performance"
    elif has_volume:
        intent = "traffic_volume"
    else:
        intent = "ambiguous_analytics"

    if start_date is None:
        return RouterDecision(
            intent=intent,
            traffic_source=traffic_source,
            needs_clarification=True,
            clarification_reason="missing_dates",
            response_message=MISSING_DATES_MESSAGE,
        )

    return RouterDecision(
        intent=intent,
        traffic_source=traffic_source,
        start_date=start_date,
        end_date=end_date,
    )


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

        base_decision = _fake_classify(question)

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
            combined_decision = _fake_classify(combined)
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
