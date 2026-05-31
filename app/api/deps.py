from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Body, Depends, Header
from pydantic import BaseModel

from app.agent.graph import get_persistent_analytics_graph
from app.infra.config import Settings
from app.infra.env import get_settings
from app.api.schemas import QueryRequest

LLM_TIMEOUT_ERROR_MESSAGE = (
    "Nao consegui concluir a analise agora porque o provedor de IA excedeu o "
    "tempo limite. Tente novamente em instantes."
)

SettingsDep = Annotated[Settings, Depends(get_settings)]
QueryRequestBody = Annotated[
    QueryRequest,
    Body(
        description=(
            "Pergunta do usuario final sobre trafego, pedidos ou receita por canal."
        )
    ),
]


class HealthResponse(BaseModel):
    status: str
    environment: str


@lru_cache
def get_query_graph() -> object:
    """Return the cached analytics graph used by HTTP request handlers."""
    return get_persistent_analytics_graph()


AnalyticsGraphDep = Annotated[object, Depends(get_query_graph)]
DebugHeader = Annotated[
    bool,
    Header(
        alias="X-Debug",
        description="Quando verdadeiro, inclui detalhes diagnosticos opcionais na resposta.",
    ),
]
