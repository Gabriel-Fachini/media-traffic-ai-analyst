from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class DateRangeInput(BaseModel):
    """Shared date range for analytics tools."""

    start_date: date = Field(
        description="Data inicial obrigatoria no formato YYYY-MM-DD, sem horario."
    )
    end_date: date = Field(
        description="Data final obrigatoria no formato YYYY-MM-DD, sem horario."
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_iso_date(cls, value: Any) -> date:
        if isinstance(value, datetime):
            raise ValueError("Use somente data no formato YYYY-MM-DD, sem horario.")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Data invalida. Use o formato YYYY-MM-DD.") from exc
        raise ValueError("Data invalida. Use o formato YYYY-MM-DD.")

    @model_validator(mode="after")
    def validate_date_range(self) -> DateRangeInput:
        if self.start_date > self.end_date:
            raise ValueError("start_date deve ser menor ou igual a end_date.")
        return self


class ToolInputBase(DateRangeInput):
    """Common optional filter used by analytics tools."""

    traffic_source: str | None = Field(
        default=None,
        description=(
            "Filtro opcional por um unico canal de trafego, por exemplo Search, "
            "Organic ou Facebook. Nao envie lista de canais."
        ),
    )

    @field_validator("traffic_source", mode="before")
    @classmethod
    def normalize_traffic_source(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("traffic_source deve ser uma string.")

        cleaned = value.strip()
        return cleaned or None


class TrafficVolumeInput(ToolInputBase):
    """Input contract for traffic volume analysis."""


class ChannelPerformanceInput(ToolInputBase):
    """Input contract for channel performance analysis."""


class TrafficVolumeRow(BaseModel):
    """Aggregated users by traffic source."""

    traffic_source: str = Field(description="Canal de origem do trafego.")
    user_count: int = Field(ge=0, description="Quantidade de usuarios unicos.")

    model_config = ConfigDict(extra="forbid")


class ChannelPerformanceRow(BaseModel):
    """Aggregated orders and revenue by traffic source."""

    traffic_source: str = Field(description="Canal de origem do trafego.")
    total_orders: int = Field(ge=0, description="Total de pedidos no periodo.")
    total_revenue: Decimal = Field(
        ge=0,
        description="Receita total do canal no periodo.",
    )

    model_config = ConfigDict(extra="forbid")


class TrafficVolumeOutput(DateRangeInput):
    """Output contract for traffic volume tool."""

    traffic_source: str | None = Field(
        default=None,
        description="Filtro aplicado no request, quando existir.",
    )
    rows: list[TrafficVolumeRow] = Field(
        default_factory=list,
        description="Lista agregada de volume de usuarios por canal.",
    )


class ChannelPerformanceOutput(DateRangeInput):
    """Output contract for channel performance tool."""

    traffic_source: str | None = Field(
        default=None,
        description="Filtro aplicado no request, quando existir.",
    )
    rows: list[ChannelPerformanceRow] = Field(
        default_factory=list,
        description="Lista agregada de pedidos e receita por canal.",
    )
