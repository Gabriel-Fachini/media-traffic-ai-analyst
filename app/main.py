from __future__ import annotations

from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from app.schemas import QueryRequest, QueryResponse
from app.utils.config import Settings, get_settings

app = FastAPI(title="Media Traffic AI Analyst")

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


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)


@app.post(
    "/query",
    response_model=QueryResponse,
    tags=["query"],
    summary="Recebe uma pergunta de analytics e retorna o contrato final da API",
    responses={
        status.HTTP_501_NOT_IMPLEMENTED: {
            "description": "Fluxo de execucao do grafo ainda sera conectado na task 4.2."
        }
    },
)
def query_analytics(request: QueryRequestBody) -> QueryResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "O endpoint /query ja expõe o contrato HTTP no Swagger, mas a execucao "
            "do grafo sera conectada na task 4.2."
        ),
    )
