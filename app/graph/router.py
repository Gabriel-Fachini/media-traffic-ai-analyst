from __future__ import annotations

from datetime import date
import re
import unicodedata
from typing import Literal

from app.schemas.router import RouterDecision, RouterNormalizedParams

DATE_TOKEN_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DIMENSION_REQUEST_PATTERN = re.compile(
    r"\b(?:por|by|per)\s+([a-z0-9_]+(?:\s+[a-z0-9_]+)?)\b"
)
QUESTION_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
SUPPORTED_CHANNEL_TOKENS = frozenset(
    {
        "canal",
        "canais",
        "channel",
        "channels",
    }
)
SUPPORTED_VOLUME_SIGNAL_TOKENS = frozenset(
    {
        "trafego",
        "traffic",
        "volume",
    }
)
SUPPORTED_USER_METRIC_TOKENS = frozenset(
    {
        "usuario",
        "usuarios",
        "user",
        "users",
    }
)
SUPPORTED_PERFORMANCE_METRIC_TOKENS = frozenset(
    {
        "pedido",
        "pedidos",
        "order",
        "orders",
        "receita",
        "revenue",
        "ranking",
        "performance",
        "desempenho",
        "melhor",
        "top",
    }
)
SUPPORTED_SOURCE_TOKENS = frozenset(
    {
        "search",
        "organic",
        "facebook",
        "instagram",
    }
)
SUPPORTED_COMPARISON_TOKENS = frozenset(
    {
        "compare",
        "comparar",
        "comparacao",
        "comparison",
        "versus",
        "vs",
    }
)
SUPPORTED_ANALYTICS_DIMENSION_TOKENS = frozenset(
    {
        "canal",
        "canais",
        "channel",
        "channels",
        "origem",
        "origens",
        "source",
        "sources",
        "traffic_source",
        "search",
        "organic",
        "facebook",
        "instagram",
    }
)
UNSUPPORTED_METRIC_TOKENS = frozenset(
    {
        "cac",
        "roas",
        "roi",
        "ltv",
        "ctr",
        "cpc",
        "cpm",
        "impressao",
        "impressoes",
        "impression",
        "impressions",
        "clique",
        "cliques",
        "click",
        "clicks",
        "campanha",
        "campanhas",
        "campaign",
        "campaigns",
        "anuncio",
        "anuncios",
        "ad",
        "ads",
        "criativo",
        "criativos",
        "creative",
        "creatives",
        "empresa",
        "empresas",
        "company",
        "companies",
    }
)

MISSING_DATES_MESSAGE = (
    "Preciso que voce informe start_date e end_date no formato YYYY-MM-DD para eu "
    "consultar os dados. Exemplo: 2024-01-01 ate 2024-01-31."
)
INVALID_DATES_MESSAGE = (
    "As datas informadas sao invalidas. Use start_date e end_date reais no formato "
    "YYYY-MM-DD, por exemplo 2024-01-01 ate 2024-01-31."
)
UNSUPPORTED_DIMENSION_MESSAGE = (
    "No MVP atual eu so consigo analisar trafego, pedidos e receita por canal "
    "(traffic_source). Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe start_date e end_date em YYYY-MM-DD."
)
EMPTY_QUESTION_MESSAGE = (
    "Envie uma pergunta sobre trafego ou receita por canal para eu montar a analise."
)
OUT_OF_SCOPE_MESSAGE = (
    "Consigo ajudar apenas com analises de trafego, pedidos e receita por canal "
    "no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe start_date e end_date em YYYY-MM-DD."
)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).lower()


def _extract_iso_dates(question: str) -> list[str]:
    return DATE_TOKEN_PATTERN.findall(question)


def _extract_requested_dimensions(question: str) -> list[str]:
    normalized_question = _normalize_text(question)
    return [
        requested_dimension.strip().replace(" ", "_")
        for requested_dimension in DIMENSION_REQUEST_PATTERN.findall(normalized_question)
    ]


def _extract_valid_and_invalid_iso_dates(
    question: str,
) -> tuple[list[date], list[str]]:
    valid_dates: list[date] = []
    invalid_dates: list[str] = []

    for date_token in _extract_iso_dates(question):
        try:
            valid_dates.append(date.fromisoformat(date_token))
        except ValueError:
            invalid_dates.append(date_token)

    return valid_dates, invalid_dates


def _extract_question_tokens(question: str) -> set[str]:
    return set(QUESTION_TOKEN_PATTERN.findall(_normalize_text(question)))


def _extract_normalized_traffic_source(question: str) -> str | None:
    source_aliases = {
        "search": "Search",
        "organic": "Organic",
        "facebook": "Facebook",
        "instagram": "Instagram",
    }
    found_sources: list[str] = []

    for token in QUESTION_TOKEN_PATTERN.findall(_normalize_text(question)):
        normalized_source = source_aliases.get(token)
        if normalized_source is None or normalized_source in found_sources:
            continue
        found_sources.append(normalized_source)

    if len(found_sources) == 1:
        return found_sources[0]

    return None


def _question_requests_unsupported_dimension(question: str) -> bool:
    requested_dimensions = _extract_requested_dimensions(question)
    if not requested_dimensions:
        return False

    return any(
        requested_dimension not in SUPPORTED_ANALYTICS_DIMENSION_TOKENS
        for requested_dimension in requested_dimensions
    )


def _question_supports_date_clarification(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    if _question_requests_unsupported_dimension(question):
        return False

    has_performance_metric = bool(
        question_tokens & SUPPORTED_PERFORMANCE_METRIC_TOKENS
    )
    has_user_metric = bool(question_tokens & SUPPORTED_USER_METRIC_TOKENS)
    has_channel_context = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
        )
    )

    return has_performance_metric or (has_user_metric and has_channel_context)


def _question_is_supported_channel_comparison(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    has_comparison_signal = bool(question_tokens & SUPPORTED_COMPARISON_TOKENS)
    supported_sources_mentioned = question_tokens & SUPPORTED_SOURCE_TOKENS
    return has_comparison_signal and len(supported_sources_mentioned) >= 2


def _resolve_router_intent(question: str) -> Literal[
    "traffic_volume", "channel_performance", "out_of_scope"
]:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return "out_of_scope"

    if _question_requests_unsupported_dimension(question):
        return "out_of_scope"

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return "out_of_scope"

    if _question_is_supported_channel_comparison(question):
        return "channel_performance"

    if question_tokens & SUPPORTED_PERFORMANCE_METRIC_TOKENS:
        return "channel_performance"

    if _question_supports_date_clarification(question):
        return "traffic_volume"

    return "out_of_scope"


def _build_normalized_params(question: str) -> RouterNormalizedParams:
    valid_dates, _ = _extract_valid_and_invalid_iso_dates(question)
    start_date = valid_dates[0] if len(valid_dates) >= 1 else None
    end_date = valid_dates[1] if len(valid_dates) >= 2 else None
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        start_date = None
        end_date = None

    return RouterNormalizedParams(
        traffic_source=_extract_normalized_traffic_source(question),
        start_date=start_date,
        end_date=end_date,
    )


def build_router_decision(question: str) -> RouterDecision:
    if not question:
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=RouterNormalizedParams(),
            refusal_reason="empty_question",
            response_message=EMPTY_QUESTION_MESSAGE,
        )

    normalized_params = _build_normalized_params(question)
    intent = _resolve_router_intent(question)

    if _question_requests_unsupported_dimension(question):
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=normalized_params,
            refusal_reason="unsupported_dimension",
            response_message=UNSUPPORTED_DIMENSION_MESSAGE,
        )

    question_tokens = _extract_question_tokens(question)
    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=normalized_params,
            refusal_reason="unsupported_metric",
            response_message=UNSUPPORTED_DIMENSION_MESSAGE,
        )

    if intent == "out_of_scope":
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=normalized_params,
            refusal_reason="out_of_scope",
            response_message=OUT_OF_SCOPE_MESSAGE,
        )

    valid_dates, invalid_dates = _extract_valid_and_invalid_iso_dates(question)
    if invalid_dates:
        return RouterDecision(
            intent=intent,
            normalized_params=normalized_params,
            needs_clarification=True,
            clarification_reason="invalid_dates",
            response_message=INVALID_DATES_MESSAGE,
        )

    if len(valid_dates) < 2:
        return RouterDecision(
            intent=intent,
            normalized_params=normalized_params,
            needs_clarification=True,
            clarification_reason="missing_dates",
            response_message=MISSING_DATES_MESSAGE,
        )

    if valid_dates[0] > valid_dates[1]:
        return RouterDecision(
            intent=intent,
            normalized_params=RouterNormalizedParams(
                traffic_source=normalized_params.traffic_source
            ),
            needs_clarification=True,
            clarification_reason="invalid_dates",
            response_message=INVALID_DATES_MESSAGE,
        )

    return RouterDecision(
        intent=intent,
        normalized_params=normalized_params,
    )


__all__ = [
    "EMPTY_QUESTION_MESSAGE",
    "INVALID_DATES_MESSAGE",
    "MISSING_DATES_MESSAGE",
    "OUT_OF_SCOPE_MESSAGE",
    "UNSUPPORTED_DIMENSION_MESSAGE",
    "build_router_decision",
]
