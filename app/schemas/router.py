from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RouterIntent = Literal[
    "traffic_volume",
    "channel_performance",
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
    """Normalized router parameters extracted from the user question."""

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
    """Explicit decision contract produced by the router step."""

    intent: RouterIntent = Field(
        description="Intencao classificada pelo roteador para a pergunta atual."
    )
    normalized_params: RouterNormalizedParams = Field(
        default_factory=RouterNormalizedParams,
        description="Parametros normalizados extraidos da pergunta.",
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
