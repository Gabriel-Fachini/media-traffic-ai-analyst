from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RouterIntent = Literal[
    "traffic_volume",
    "channel_performance",
    "strategy_follow_up",
    "diagnostic_follow_up",
    "ambiguous_analytics",
    "out_of_scope",
]
RouterClarificationReason = Literal[
    "missing_dates",
    "invalid_dates",
    "ambiguous_metric",
]
RouterRefusalReason = Literal[
    "empty_question",
    "out_of_scope",
    "unsupported_dimension",
    "unsupported_metric",
    "unsupported_traffic_source",
]


class RouterNormalizedParams(BaseModel):
    """Normalized router parameters. Used by deterministic_router as a value object."""

    traffic_source: str | None = Field(
        default=None,
        description=(
            "Canal normalizado quando a pergunta menciona exatamente um canal suportado."
        ),
    )
    start_date: date | None = Field(
        default=None,
        description="Data inicial normalizada quando a pergunta traz uma data valida.",
    )
    end_date: date | None = Field(
        default=None,
        description="Data final normalizada quando a pergunta traz uma data valida.",
    )

    model_config = ConfigDict(extra="forbid")


class RouterDecision(BaseModel):
    """Explicit decision contract produced by the router step.

    Fields are flat so that LLMs which do not support deeply nested JSON schemas
    (e.g. Ollama models) can populate them without wrapping in a nested object.
    The ``normalized_params`` property provides backward-compatible access.
    """

    intent: RouterIntent = Field(
        description="Intencao classificada pelo roteador para a pergunta atual."
    )
    traffic_source: str | None = Field(
        default=None,
        description=(
            "Canal normalizado quando a pergunta menciona exatamente um canal suportado. "
            "Valores aceitos: Search, Organic, Facebook, Instagram. Nulo para todos os canais."
        ),
    )
    start_date: date | None = Field(
        default=None,
        description="Data inicial normalizada (YYYY-MM-DD). Nulo se ausente na pergunta.",
    )
    end_date: date | None = Field(
        default=None,
        description="Data final normalizada (YYYY-MM-DD). Nulo se ausente na pergunta.",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Indica se o fluxo deve pedir esclarecimento antes de continuar.",
    )
    clarification_reason: RouterClarificationReason | None = Field(
        default=None,
        description="Motivo estruturado do pedido de clarificacao, quando existir.",
    )
    refusal_reason: RouterRefusalReason | None = Field(
        default=None,
        description="Motivo estruturado da recusa, quando existir.",
    )
    response_message: str | None = Field(
        default=None,
        description=(
            "Mensagem pronta para o usuario quando a decisao do roteador encerra "
            "o turno com clarificacao ou recusa."
        ),
    )

    model_config = ConfigDict(extra="forbid")

    @property
    def normalized_params(self) -> RouterNormalizedParams:
        """Backward-compatible view of the flat date/source fields as a value object."""
        return RouterNormalizedParams(
            traffic_source=self.traffic_source,
            start_date=self.start_date,
            end_date=self.end_date,
        )

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> RouterDecision:
        if self.needs_clarification:
            if self.clarification_reason is None:
                raise ValueError(
                    "clarification_reason e obrigatorio quando needs_clarification=True."
                )
            if self.refusal_reason is not None:
                raise ValueError(
                    "refusal_reason deve ser nulo quando needs_clarification=True."
                )
            if self.response_message is None:
                raise ValueError(
                    "response_message e obrigatoria quando needs_clarification=True."
                )
            return self

        if self.clarification_reason is not None:
            raise ValueError(
                "clarification_reason deve ser nulo quando needs_clarification=False."
            )

        if self.refusal_reason is not None:
            if self.intent != "out_of_scope":
                raise ValueError(
                    "Somente intent='out_of_scope' pode carregar refusal_reason."
                )
            if self.response_message is None:
                raise ValueError(
                    "response_message e obrigatoria quando refusal_reason estiver definida."
                )

        return self
