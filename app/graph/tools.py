from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput
from app.tools import channel_performance_analyzer, traffic_volume_analyzer


def _run_traffic_volume_analyzer(
    start_date: date,
    end_date: date,
    traffic_source: str | None = None,
) -> dict[str, Any]:
    result = traffic_volume_analyzer(
        TrafficVolumeInput(
            traffic_source=traffic_source,
            start_date=start_date,
            end_date=end_date,
        )
    )
    return result.model_dump(mode="json")


def _run_channel_performance_analyzer(
    start_date: date,
    end_date: date,
    traffic_source: str | None = None,
) -> dict[str, Any]:
    result = channel_performance_analyzer(
        ChannelPerformanceInput(
            traffic_source=traffic_source,
            start_date=start_date,
            end_date=end_date,
        )
    )
    return result.model_dump(mode="json")


TRAFFIC_VOLUME_ANALYZER_TOOL = StructuredTool.from_function(
    func=_run_traffic_volume_analyzer,
    name="traffic_volume_analyzer",
    description=(
        "Use somente para perguntas sobre volume de usuarios por canal no periodo "
        "informado. Retorna user_count agregado por traffic_source. Nao use para "
        "receita, pedidos, ticket medio ou desempenho financeiro. Se a pergunta "
        "nao trouxer start_date e end_date, peca clarificacao antes de chamar a "
        "tool. traffic_source e opcional e aceita somente um canal por vez."
    ),
    args_schema=TrafficVolumeInput,
)


CHANNEL_PERFORMANCE_ANALYZER_TOOL = StructuredTool.from_function(
    func=_run_channel_performance_analyzer,
    name="channel_performance_analyzer",
    description=(
        "Use somente para perguntas sobre receita, pedidos, desempenho "
        "financeiro, ranking de canais ou melhor performance no periodo "
        "informado. Retorna total_orders e total_revenue agregados por "
        "traffic_source. Nao use para volume de usuarios. Se a pergunta nao "
        "trouxer start_date e end_date, peca clarificacao antes de chamar a "
        "tool. traffic_source e opcional e aceita somente um canal por vez."
    ),
    args_schema=ChannelPerformanceInput,
)


ANALYTICS_TOOLS: tuple[BaseTool, ...] = (
    TRAFFIC_VOLUME_ANALYZER_TOOL,
    CHANNEL_PERFORMANCE_ANALYZER_TOOL,
)


def get_analytics_tools() -> tuple[BaseTool, ...]:
    """Return the analytics tools exposed to the LLM."""

    return ANALYTICS_TOOLS
