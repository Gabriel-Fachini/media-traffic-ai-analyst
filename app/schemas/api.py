from __future__ import annotations

from typing import Literal

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
    thread_id: str | None = Field(
        default=None,
        description=(
            "Identificador opcional da conversa. Reutilize o thread_id retornado "
            "pela API para manter continuidade multi-turn entre chamadas."
        ),
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

    @field_validator("thread_id")
    @classmethod
    def normalize_thread_id(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None


class QueryMetadata(BaseModel):
    """Metadata returned with each API query response."""

    thread_id: str = Field(
        description="Identificador da conversa a ser reutilizado em chamadas futuras."
    )
    thread_id_source: Literal["generated", "provided"] = Field(
        description="Indica se o thread_id foi gerado pela API ou enviado pelo cliente."
    )
    context_message_count: int = Field(
        ge=0,
        description="Quantidade total de mensagens atualmente armazenadas no contexto da conversa.",
    )

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """HTTP error contract for API failures."""

    detail: str = Field(
        description="Mensagem resumida do erro retornado pela API."
    )

    model_config = ConfigDict(extra="forbid")


class QueryResponse(BaseModel):
    """HTTP output contract for analytics answers."""

    answer: str = Field(
        description="Resposta final em linguagem natural para o usuario."
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Lista das tools utilizadas para produzir a resposta.",
    )
    metadata: QueryMetadata | None = Field(
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
                "metadata": {
                    "thread_id": "analytics-session-001",
                    "thread_id_source": "provided",
                    "context_message_count": 6,
                },
            }
        },
    )
