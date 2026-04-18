from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.graph import invoke_analytics_graph
from app.graph.llm import LlmTimeoutError
from app.graph.workflow import get_persistent_analytics_graph
from app.schemas import ErrorResponse, QueryMetadata, QueryRequest, QueryResponse
from app.utils.config import Settings, get_settings

app = FastAPI(title="Media Traffic AI Analyst")

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
    return get_persistent_analytics_graph()


AnalyticsGraphDep = Annotated[object, Depends(get_query_graph)]


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)


@app.post(
    "/query",
    response_model=QueryResponse,
    tags=["query"],
    summary="Recebe uma pergunta de analytics e retorna a resposta do agente",
    responses={
        500: {
            "model": ErrorResponse,
            "description": "Falha temporaria ao consultar ou sintetizar via LLM.",
        }
    },
)
def query_analytics(
    request: QueryRequestBody,
    graph: AnalyticsGraphDep,
) -> QueryResponse:
    thread_id = request.thread_id or str(uuid4())
    try:
        state = invoke_analytics_graph(
            request.question,
            thread_id=thread_id,
            graph=graph,
        )
    except LlmTimeoutError as exc:
        raise HTTPException(status_code=500, detail=LLM_TIMEOUT_ERROR_MESSAGE) from exc

    messages = state.get("messages", [])

    return QueryResponse(
        answer=state.get("final_answer", ""),
        tools_used=state.get("tools_used", []),
        metadata=QueryMetadata(
            thread_id=thread_id,
            thread_id_source="provided" if request.thread_id else "generated",
            context_message_count=len(messages),
        ),
    )
