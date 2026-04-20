from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.graph import AnalyticsGraphState, invoke_analytics_graph
from app.graph.llm import LlmTimeoutError
from app.graph.workflow import get_persistent_analytics_graph
from app.schemas import (
    DebugError,
    DebugInfo,
    ErrorResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
)
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
DebugHeader = Annotated[
    bool,
    Header(
        alias="X-Debug",
        description="Quando verdadeiro, inclui detalhes diagnosticos opcionais na resposta.",
    ),
]


def _build_debug_info_from_state(state: AnalyticsGraphState) -> DebugInfo | None:
    raw_errors = state.get("debug_errors", [])
    errors: list[DebugError] = []

    for raw_error in raw_errors:
        try:
            errors.append(DebugError.model_validate(raw_error))
        except ValidationError:
            continue

    resolved_question = state.get("resolved_question") or None
    router_decision = state.get("router_decision")

    if not errors and resolved_question is None and router_decision is None:
        return None

    return DebugInfo(
        resolved_question=resolved_question,
        router_decision=router_decision,
        errors=errors,
    )


def _build_timeout_debug_info(
    request: QueryRequest,
    exc: LlmTimeoutError,
) -> DebugInfo:
    return DebugInfo(
        resolved_question=request.question,
        errors=[
            DebugError(
                source="api",
                message=exc.debug_message,
                error_type=exc.error_type or type(exc).__name__,
            )
        ],
    )


def _build_error_response(
    detail: str,
    *,
    debug: DebugInfo | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=detail, debug=debug).model_dump(mode="json"),
    )


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
    debug: DebugHeader = False,
) -> QueryResponse | JSONResponse:
    thread_id = request.thread_id or str(uuid4())
    try:
        state = invoke_analytics_graph(
            request.question,
            thread_id=thread_id,
            graph=graph,
        )
    except LlmTimeoutError as exc:
        debug_info = _build_timeout_debug_info(request, exc) if debug else None
        return _build_error_response(LLM_TIMEOUT_ERROR_MESSAGE, debug=debug_info)

    messages = state.get("messages", [])
    debug_info = _build_debug_info_from_state(state) if debug else None

    return QueryResponse(
        answer=state.get("final_answer", ""),
        tools_used=state.get("tools_used", []),
        metadata=QueryMetadata(
            thread_id=thread_id,
            thread_id_source="provided" if request.thread_id else "generated",
            context_message_count=len(messages),
            debug=debug_info,
        ),
    )
