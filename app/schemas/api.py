from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    """HTTP input contract for analytics questions."""

    question: str = Field(
        max_length=1000,
        description=(
            "Pergunta em linguagem natural sobre trafego, pedidos ou receita por "
            "canal. Quando depender de dados, informe start_date e end_date em "
            "YYYY-MM-DD na propria pergunta."
        ),
        examples=[
            "Quais canais tiveram melhor desempenho de receita entre 2024-01-01 e 2024-01-31?"
        ],
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "question": (
                    "Qual foi o volume de usuarios de Search entre 2024-01-01 e "
                    "2024-01-31?"
                )
            }
        },
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question nao pode ser vazia.")
        return cleaned


class QueryResponse(BaseModel):
    """HTTP output contract for analytics answers."""

    answer: str = Field(
        description="Resposta final em linguagem natural para o usuario."
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Lista das tools utilizadas para produzir a resposta.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Metadados opcionais da execucao do fluxo.",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "answer": (
                    "Search liderou o periodo em volume de usuarios, indicando que "
                    "o canal segue como principal motor de aquisicao na janela analisada."
                ),
                "tools_used": ["traffic_volume_analyzer"],
                "metadata": {"sources_compared": ["Search", "Organic", "Facebook"]},
            }
        },
    )
