from __future__ import annotations

from datetime import date, datetime, timedelta
import re
import unicodedata
from typing import Literal

from app.schemas.router import RouterDecision, RouterNormalizedParams

EXPLICIT_DATE_TOKEN_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{2}(?:\d{2})?)\b"
)
DIMENSION_REQUEST_PATTERN = re.compile(
    r"\b(?:por|by|per)\s+([a-z0-9_]+)(?:\s+([a-z0-9_]+))?\b"
)
SOURCE_FILTER_PATTERN = re.compile(r"\b(?:de|do|da|from)\s+([a-z0-9_]+)\b")
QUESTION_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
YESTERDAY_PATTERN = re.compile(r"\bontem\b")
THIS_MONTH_PATTERN = re.compile(r"\beste\s+mes\b")
LAST_MONTH_PATTERN = re.compile(r"\bultimo\s+mes\b")
LAST_N_DAYS_PATTERN = re.compile(r"\bultimos?\s+(\d+)\s+dias?\b")
CALENDAR_MONTH_COMPLETE_PATTERN = re.compile(
    r"\bmes\s+calendario\s+completo\b|\bmes\s+completo\b"
)
TEMPORAL_CONTEXT_PATTERN = re.compile(
    r"\b(?:entre|from)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\s+(?:e|a|ate|to)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\b"
    r"|\b(?:entre|from)\s+\d{4}-\d{2}-\d{2}\s+(?:e|a|ate|to)\s+\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:em|in|on|de|do|da|from)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\b"
    r"|\b(?:em|in|on|de|do|da|from)\s+\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:no|na|nos|nas|em|in)\s+ultimo\s+mes\b"
    r"|\b(?:no|na|nos|nas|em|in)\s+este\s+mes\b"
    r"|\bmes\s+calendario\s+completo\b"
    r"|\bmes\s+completo\b"
    r"|\b(?:nos|nas|em|in)\s+ultimos?\s+\d+\s+dias?\b"
    r"|\bontem\b",
    re.IGNORECASE,
)
TEMPORAL_SOURCE_FILTER_IGNORED_TOKENS = frozenset(
    {
        "ontem",
        "este",
        "esta",
        "ultimo",
        "ultima",
        "ultimos",
        "ultimas",
    }
)
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
        "venda",
        "vendas",
        "vendeu",
        "faturou",
        "faturamento",
        "faturar",
        "financeiro",
        "financeira",
    }
)
AMBIGUOUS_ANALYTICS_HINT_TOKENS = frozenset(
    {
        "performou",
        "performar",
        "mostre",
        "mostrar",
        "mostra",
        "melhores",
        "resultado",
        "resultados",
        "pior",
        "piores",
    }
)
SUPPORTED_SOURCE_TOKENS = frozenset(
    {
        "search",
        "google",
        "googleads",
        "google_ads",
        "adwords",
        "organic",
        "seo",
        "facebook",
        "fb",
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
STRATEGY_FOLLOW_UP_TOKENS = frozenset(
    {
        "acao",
        "acoes",
        "analise",
        "analises",
        "aumentar",
        "crescer",
        "dependencia",
        "dependente",
        "diminuir",
        "detalhar",
        "detalhe",
        "diversificar",
        "expandir",
        "expanda",
        "estrategia",
        "estrategias",
        "fortalecer",
        "melhorar",
        "melhoria",
        "monte",
        "otimizacao",
        "otimizar",
        "passo",
        "passos",
        "plano",
        "priorizar",
        "proximo",
        "proximos",
        "reduzir",
        "recomendacao",
        "recomendacoes",
        "recomenda",
        "recomendar",
        "retorne",
        "retornar",
        "sugestao",
        "sugestoes",
    }
)
FOLLOW_UP_ACTION_TOKENS = frozenset(
    {
        "aprofunde",
        "aprofundar",
        "continue",
        "continuar",
        "descreva",
        "desenvolva",
        "detalhar",
        "detalhe",
        "expanda",
        "expandir",
        "monte",
        "retorne",
        "retornar",
    }
)
FOLLOW_UP_STRATEGY_OBJECT_TOKENS = frozenset(
    {
        "acao",
        "acoes",
        "analise",
        "analises",
        "estrategia",
        "estrategias",
        "plano",
        "prioridade",
        "prioridades",
        "recomendacao",
        "recomendacoes",
        "sugestao",
        "sugestoes",
    }
)
GENERIC_CONTEXTUAL_FOLLOW_UP_ACTION_TOKENS = frozenset(
    {
        "ajuda",
        "ajudar",
        "ajude",
        "continue",
        "continuar",
        "faca",
        "fazer",
        "monte",
        "mostra",
        "mostrar",
        "mostre",
        "responda",
        "responder",
        "retorne",
        "retornar",
        "segue",
        "seguir",
        "siga",
        "traga",
    }
)
GENERIC_CONTEXTUAL_FOLLOW_UP_REFERENCE_TOKENS = frozenset(
    {
        "ai",
        "entao",
        "essa",
        "esse",
        "isso",
        "leitura",
    }
)
CONTEXTUAL_DIAGNOSTIC_SIGNAL_TOKENS = frozenset(
    {
        "abaixo",
        "acima",
        "comparacao",
        "comparar",
        "comparativo",
        "desempenho",
        "melhor",
        "melhores",
        "outro",
        "outra",
        "outros",
        "outras",
        "pior",
        "piores",
        "performando",
        "performar",
        "performou",
    }
)
DIAGNOSTIC_FOLLOW_UP_TOKENS = frozenset(
    {
        "causa",
        "causas",
        "diagnostica",
        "diagnostico",
        "entender",
        "explica",
        "explicacao",
        "explicar",
        "fator",
        "fatores",
        "hipotese",
        "hipoteses",
        "motivo",
        "motivos",
        "razao",
        "razoes",
    }
)
DIAGNOSTIC_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:por que|porque|o que explica|como explicar|qual a explicacao)\b"
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
DIMENSION_REQUEST_IGNORED_TOKENS = frozenset(
    {
        "a",
        "ao",
        "as",
        "ate",
        "com",
        "como",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "entre",
        "na",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "para",
        "por",
        "qual",
        "que",
        "se",
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
SOURCE_ALIASES = {
    "search": "Search",
    "google": "Search",
    "googleads": "Search",
    "google_ads": "Search",
    "adwords": "Search",
    "organic": "Organic",
    "seo": "Organic",
    "facebook": "Facebook",
    "fb": "Facebook",
    "instagram": "Instagram",
}
SOURCE_FILTER_IGNORED_TOKENS = frozenset(
    SUPPORTED_CHANNEL_TOKENS
    | SUPPORTED_VOLUME_SIGNAL_TOKENS
    | SUPPORTED_USER_METRIC_TOKENS
    | SUPPORTED_PERFORMANCE_METRIC_TOKENS
    | {
        "a",
        "as",
        "essa",
        "esse",
        "isso",
        "midia",
        "media",
        "growth",
        "mais",
        "menos",
        "os",
        "outro",
        "outra",
        "outros",
        "outras",
        "origem",
        "origens",
        "qual",
        "quais",
        "que",
        "quem",
        "source",
        "sources",
        "traffic_source",
    }
)

MISSING_DATES_MESSAGE = (
    "Preciso que voce informe o periodo para eu consultar os dados. Voce pode usar "
    "YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou periodos relativos como ontem, este "
    "mes, ultimo mes e ultimos 7 dias."
)
INVALID_DATES_MESSAGE = (
    "As datas informadas sao invalidas. Use datas reais em YYYY-MM-DD, DD/MM/AAAA, "
    "DD/MM/AA ou periodos relativos suportados, por exemplo 2024-01-01 ate "
    "2024-01-31, 01/04/2026 ate 20/04/2026, 01/04/26 ou ultimos 7 dias."
)
UNSUPPORTED_METRIC_MESSAGE = (
    "No MVP atual eu so consigo analisar volume de trafego, pedidos e receita por "
    "canal com base no schema disponivel. Reformule a pergunta sem metricas como "
    "ROAS, CAC, CTR ou outras metricas que nao existem no dataset atual."
)
UNSUPPORTED_DIMENSION_MESSAGE = (
    "No MVP atual eu so consigo analisar trafego, pedidos e receita por canal "
    "(traffic_source). Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA "
    "ou com periodos relativos suportados."
)
EMPTY_QUESTION_MESSAGE = (
    "Envie uma pergunta sobre trafego ou receita por canal para eu montar a analise."
)
OUT_OF_SCOPE_MESSAGE = (
    "Consigo ajudar apenas com analises de trafego, pedidos e receita por canal "
    "no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta "
    "depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA "
    "ou com periodos relativos suportados."
)


def _build_unsupported_traffic_source_message(source_token: str) -> str:
    humanized_source = source_token.replace("_", " ").title()
    return (
        f"No MVP atual eu nao consigo filtrar pelo canal {humanized_source}. "
        "Use um canal suportado como Search, Organic, Facebook ou Instagram, "
        "ou remova o filtro especifico para comparar os canais no periodo."
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).lower()


def _resolve_reference_date(reference_date: date | None) -> date:
    return reference_date or date.today()


def _extract_explicit_date_tokens(question: str) -> list[str]:
    return [
        match.group(0)
        for match in EXPLICIT_DATE_TOKEN_PATTERN.finditer(question)
    ]


def _extract_requested_dimensions(question: str) -> list[str]:
    normalized_question = _normalize_text(question)
    requested_dimensions: list[str] = []

    for first_token, second_token in DIMENSION_REQUEST_PATTERN.findall(normalized_question):
        if first_token in DIMENSION_REQUEST_IGNORED_TOKENS:
            continue

        supported_dimension_candidates = []
        if second_token:
            supported_dimension_candidates.append(f"{first_token}_{second_token}")
        supported_dimension_candidates.append(first_token)

        matched_supported_dimension = next(
            (
                candidate
                for candidate in supported_dimension_candidates
                if candidate in SUPPORTED_ANALYTICS_DIMENSION_TOKENS
            ),
            None,
        )
        if matched_supported_dimension is not None:
            if matched_supported_dimension not in requested_dimensions:
                requested_dimensions.append(matched_supported_dimension)
            continue

        if first_token not in requested_dimensions:
            requested_dimensions.append(first_token)

    return requested_dimensions


def _parse_explicit_date_token(date_token: str) -> date:
    if "-" in date_token:
        return date.fromisoformat(date_token)
    for date_format in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_token, date_format).date()
        except ValueError:
            continue
    raise ValueError("Data invalida.")


def _extract_valid_and_invalid_explicit_dates(
    question: str,
) -> tuple[list[date], list[str]]:
    valid_dates: list[date] = []
    invalid_dates: list[str] = []

    for date_token in _extract_explicit_date_tokens(question):
        try:
            valid_dates.append(_parse_explicit_date_token(date_token))
        except ValueError:
            invalid_dates.append(date_token)

    return valid_dates, invalid_dates


def _match_yesterday(reference_date: date) -> tuple[date, date]:
    yesterday = reference_date - timedelta(days=1)
    return yesterday, yesterday


def _match_this_month(reference_date: date) -> tuple[date, date]:
    return reference_date.replace(day=1), reference_date


def _match_last_month(reference_date: date) -> tuple[date, date]:
    current_month_start = reference_date.replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    return last_month_end.replace(day=1), last_month_end


def _match_calendar_month_complete(reference_date: date) -> tuple[date, date]:
    current_month_start = reference_date.replace(day=1)
    if reference_date.month == 12:
        next_month_start = date(reference_date.year + 1, 1, 1)
    else:
        next_month_start = date(reference_date.year, reference_date.month + 1, 1)
    return current_month_start, next_month_start - timedelta(days=1)


def _extract_relative_date_range(
    question: str,
    *,
    reference_date: date | None = None,
) -> tuple[tuple[date, date] | None, list[str]]:
    normalized_question = _normalize_text(question)
    resolved_reference_date = _resolve_reference_date(reference_date)
    relative_matches: list[tuple[int, tuple[date, date]]] = []
    invalid_tokens: list[str] = []

    for match in YESTERDAY_PATTERN.finditer(normalized_question):
        relative_matches.append(
            (match.start(), _match_yesterday(resolved_reference_date))
        )

    for match in THIS_MONTH_PATTERN.finditer(normalized_question):
        relative_matches.append(
            (match.start(), _match_this_month(resolved_reference_date))
        )

    for match in LAST_MONTH_PATTERN.finditer(normalized_question):
        relative_matches.append(
            (match.start(), _match_last_month(resolved_reference_date))
        )

    for match in CALENDAR_MONTH_COMPLETE_PATTERN.finditer(normalized_question):
        relative_matches.append(
            (match.start(), _match_calendar_month_complete(resolved_reference_date))
        )

    for match in LAST_N_DAYS_PATTERN.finditer(normalized_question):
        day_count = int(match.group(1))
        if day_count <= 0:
            invalid_tokens.append(match.group(0))
            continue
        relative_matches.append(
            (
                match.start(),
                (
                    resolved_reference_date - timedelta(days=day_count - 1),
                    resolved_reference_date,
                ),
            )
        )

    if not relative_matches:
        return None, invalid_tokens

    relative_matches.sort(key=lambda item: item[0])
    return relative_matches[-1][1], invalid_tokens


def _extract_question_tokens(question: str) -> set[str]:
    return set(QUESTION_TOKEN_PATTERN.findall(_normalize_text(question)))


def _question_has_supported_context(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    return bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_USER_METRIC_TOKENS
            | SUPPORTED_PERFORMANCE_METRIC_TOKENS
            | AMBIGUOUS_ANALYTICS_HINT_TOKENS
        )
    )


def _extract_source_filter_tokens(question: str) -> list[str]:
    return SOURCE_FILTER_PATTERN.findall(_normalize_text(question))


def _extract_traffic_sources(question: str) -> list[str]:
    found_sources: list[str] = []

    for token in QUESTION_TOKEN_PATTERN.findall(_normalize_text(question)):
        normalized_source = SOURCE_ALIASES.get(token)
        if normalized_source is None or normalized_source in found_sources:
            continue
        found_sources.append(normalized_source)

    return found_sources


def _extract_normalized_traffic_source(question: str) -> str | None:
    found_sources = _extract_traffic_sources(question)

    if len(found_sources) == 1:
        return found_sources[0]

    return None


def _extract_unknown_traffic_source(question: str) -> str | None:
    unknown_sources: list[str] = []

    for token in _extract_source_filter_tokens(question):
        if token in SOURCE_FILTER_IGNORED_TOKENS:
            continue
        if token.isdigit():
            continue
        if token in TEMPORAL_SOURCE_FILTER_IGNORED_TOKENS:
            continue
        if token in SOURCE_ALIASES:
            continue
        if token in unknown_sources:
            continue
        unknown_sources.append(token)

    if len(unknown_sources) == 1:
        return unknown_sources[0]

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

    has_user_metric = bool(question_tokens & SUPPORTED_USER_METRIC_TOKENS)
    has_volume_signal = bool(question_tokens & SUPPORTED_VOLUME_SIGNAL_TOKENS)
    has_channel_context = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
        )
    )

    return (has_user_metric or has_volume_signal) and has_channel_context


def _question_is_aggregate_user_volume_query(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    if _question_requests_unsupported_dimension(question):
        return False

    has_user_metric = bool(question_tokens & SUPPORTED_USER_METRIC_TOKENS)
    has_temporal_signal = question_contains_temporal_signal(question)
    has_performance_metric = bool(question_tokens & SUPPORTED_PERFORMANCE_METRIC_TOKENS)

    return has_user_metric and has_temporal_signal and not has_performance_metric


def _question_contains_metric_follow_up_signal(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    return bool(
        question_tokens
        & (
            SUPPORTED_USER_METRIC_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_PERFORMANCE_METRIC_TOKENS
        )
    )


def question_is_metric_clarification_follow_up(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False
    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False
    return _question_contains_metric_follow_up_signal(question)


def question_is_strategy_follow_up(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    has_strategy_signal = bool(question_tokens & STRATEGY_FOLLOW_UP_TOKENS)
    has_analytics_anchor = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_PERFORMANCE_METRIC_TOKENS
        )
    )
    has_contextual_strategy_request = bool(
        question_tokens & FOLLOW_UP_ACTION_TOKENS
    ) and bool(question_tokens & FOLLOW_UP_STRATEGY_OBJECT_TOKENS)
    return (has_strategy_signal and has_analytics_anchor) or has_contextual_strategy_request


def question_is_generic_contextual_follow_up(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    has_action = bool(question_tokens & GENERIC_CONTEXTUAL_FOLLOW_UP_ACTION_TOKENS)
    has_reference = bool(question_tokens & GENERIC_CONTEXTUAL_FOLLOW_UP_REFERENCE_TOKENS)
    return has_action and (has_reference or len(question_tokens) <= 3)


def question_is_contextual_diagnostic_follow_up(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    has_signal = bool(question_tokens & CONTEXTUAL_DIAGNOSTIC_SIGNAL_TOKENS)
    has_anchor = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
            | {"outro", "outra", "outros", "outras"}
        )
    )
    return has_signal and has_anchor


def question_is_diagnostic_follow_up(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    if question_tokens & UNSUPPORTED_METRIC_TOKENS:
        return False

    normalized_question = _normalize_text(question)
    has_diagnostic_signal = bool(
        question_tokens & DIAGNOSTIC_FOLLOW_UP_TOKENS
    ) or bool(DIAGNOSTIC_FOLLOW_UP_PATTERN.search(normalized_question))
    has_analytics_anchor = bool(
        question_tokens
        & (
            SUPPORTED_CHANNEL_TOKENS
            | SUPPORTED_SOURCE_TOKENS
            | SUPPORTED_VOLUME_SIGNAL_TOKENS
            | SUPPORTED_PERFORMANCE_METRIC_TOKENS
        )
    )
    return has_diagnostic_signal and has_analytics_anchor


def question_introduces_new_traffic_source(
    question: str,
    *,
    previous_traffic_source: str | None = None,
) -> bool:
    question_sources = _extract_traffic_sources(question)
    if not question_sources:
        return False

    if previous_traffic_source is None:
        return True

    return set(question_sources) != {previous_traffic_source}


def _question_is_supported_channel_comparison(question: str) -> bool:
    question_tokens = _extract_question_tokens(question)
    if not question_tokens:
        return False

    has_comparison_signal = bool(question_tokens & SUPPORTED_COMPARISON_TOKENS)
    supported_sources_mentioned = question_tokens & SUPPORTED_SOURCE_TOKENS
    return has_comparison_signal and len(supported_sources_mentioned) >= 2


def _resolve_router_intent(question: str) -> Literal[
    "traffic_volume", "channel_performance", "ambiguous_analytics", "out_of_scope"
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

    if _question_is_aggregate_user_volume_query(question):
        return "traffic_volume"

    if _question_supports_date_clarification(question):
        return "traffic_volume"

    has_temporal_signal = question_contains_temporal_signal(question)
    has_supported_context = _question_has_supported_context(question)
    has_ambiguous_hint = bool(question_tokens & AMBIGUOUS_ANALYTICS_HINT_TOKENS)
    has_source_or_channel_context = bool(
        question_tokens & (SUPPORTED_CHANNEL_TOKENS | SUPPORTED_SOURCE_TOKENS)
    )
    if has_supported_context and (
        has_ambiguous_hint or (has_source_or_channel_context and has_temporal_signal)
    ):
        return "ambiguous_analytics"

    return "out_of_scope"


def _build_normalized_params(
    question: str,
    *,
    reference_date: date | None = None,
) -> RouterNormalizedParams:
    valid_dates, _ = _extract_valid_and_invalid_explicit_dates(question)
    relative_date_range, _ = _extract_relative_date_range(
        question,
        reference_date=reference_date,
    )
    start_date = None
    end_date = None
    if len(valid_dates) >= 2:
        start_date = valid_dates[0]
        end_date = valid_dates[1]
    elif len(valid_dates) == 1:
        start_date = valid_dates[0]
        end_date = valid_dates[0]
    elif relative_date_range is not None:
        start_date, end_date = relative_date_range
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


def question_contains_temporal_signal(question: str) -> bool:
    if EXPLICIT_DATE_TOKEN_PATTERN.search(question):
        return True

    normalized_question = _normalize_text(question)
    return any(
        pattern.search(normalized_question)
        for pattern in (
            YESTERDAY_PATTERN,
            THIS_MONTH_PATTERN,
            LAST_MONTH_PATTERN,
            CALENDAR_MONTH_COMPLETE_PATTERN,
            LAST_N_DAYS_PATTERN,
        )
    )


def strip_temporal_context(question: str) -> str:
    stripped_question = TEMPORAL_CONTEXT_PATTERN.sub(" ", question)
    stripped_question = re.sub(r"\s+", " ", stripped_question)
    stripped_question = re.sub(r"\s+([?.!,;:])", r"\1", stripped_question)
    return stripped_question.strip()


def _format_guided_subject(normalized_params: RouterNormalizedParams) -> str:
    if normalized_params.traffic_source is not None:
        return f"o canal {normalized_params.traffic_source}"
    return "os canais"


def _format_guided_period(normalized_params: RouterNormalizedParams) -> str | None:
    start_date = normalized_params.start_date
    end_date = normalized_params.end_date
    if start_date is None or end_date is None:
        return None
    if start_date == end_date:
        return f"em {start_date.isoformat()}"
    return f"no periodo de {start_date.isoformat()} ate {end_date.isoformat()}"


def _build_guided_metric_clarification_message(
    normalized_params: RouterNormalizedParams,
) -> str:
    subject = _format_guided_subject(normalized_params)
    period = _format_guided_period(normalized_params)

    if period is not None:
        return (
            f"Entendi que voce quer analisar {subject} {period}, mas preciso alinhar "
            "o foco. Voce quer ver volume de usuarios ou performance financeira "
            "(receita e pedidos)?"
        )

    return (
        f"Entendi que voce quer analisar {subject}, mas preciso alinhar o foco. "
        "Voce quer ver volume de usuarios ou performance financeira (receita e "
        "pedidos)? Se quiser, ja pode responder junto com o periodo em "
        "YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com formatos relativos como ontem."
    )


def build_router_decision(
    question: str,
    *,
    reference_date: date | None = None,
) -> RouterDecision:
    if not question:
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=RouterNormalizedParams(),
            refusal_reason="empty_question",
            response_message=EMPTY_QUESTION_MESSAGE,
        )

    resolved_reference_date = _resolve_reference_date(reference_date)
    normalized_params = _build_normalized_params(
        question,
        reference_date=resolved_reference_date,
    )
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
            response_message=UNSUPPORTED_METRIC_MESSAGE,
        )

    unknown_traffic_source = _extract_unknown_traffic_source(question)
    if unknown_traffic_source is not None:
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=normalized_params,
            refusal_reason="unsupported_traffic_source",
            response_message=_build_unsupported_traffic_source_message(
                unknown_traffic_source
            ),
        )

    valid_dates, invalid_dates = _extract_valid_and_invalid_explicit_dates(question)
    _, invalid_relative_tokens = _extract_relative_date_range(
        question,
        reference_date=resolved_reference_date,
    )
    all_invalid_dates = [*invalid_dates, *invalid_relative_tokens]
    has_supported_context = _question_has_supported_context(question)
    has_reversed_explicit_dates = len(valid_dates) >= 2 and valid_dates[0] > valid_dates[1]
    if all_invalid_dates and (
        intent != "out_of_scope" or has_supported_context
    ):
        return RouterDecision(
            intent=intent,
            normalized_params=normalized_params,
            needs_clarification=True,
            clarification_reason="invalid_dates",
            response_message=INVALID_DATES_MESSAGE,
        )

    if has_reversed_explicit_dates and (
        intent != "out_of_scope" or has_supported_context
    ):
        return RouterDecision(
            intent=intent,
            normalized_params=RouterNormalizedParams(
                traffic_source=normalized_params.traffic_source
            ),
            needs_clarification=True,
            clarification_reason="invalid_dates",
            response_message=INVALID_DATES_MESSAGE,
        )

    if intent == "ambiguous_analytics":
        return RouterDecision(
            intent="ambiguous_analytics",
            normalized_params=normalized_params,
            needs_clarification=True,
            clarification_reason="ambiguous_metric",
            response_message=_build_guided_metric_clarification_message(
                normalized_params
            ),
        )

    if intent == "out_of_scope":
        return RouterDecision(
            intent="out_of_scope",
            normalized_params=normalized_params,
            refusal_reason="out_of_scope",
            response_message=OUT_OF_SCOPE_MESSAGE,
        )

    has_complete_date_range = (
        normalized_params.start_date is not None
        and normalized_params.end_date is not None
    )
    if not has_complete_date_range:
        return RouterDecision(
            intent=intent,
            normalized_params=normalized_params,
            needs_clarification=True,
            clarification_reason="missing_dates",
            response_message=MISSING_DATES_MESSAGE,
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
    "UNSUPPORTED_METRIC_MESSAGE",
    "build_router_decision",
    "question_is_contextual_diagnostic_follow_up",
    "question_is_diagnostic_follow_up",
    "question_is_generic_contextual_follow_up",
    "question_introduces_new_traffic_source",
    "question_is_metric_clarification_follow_up",
    "question_is_strategy_follow_up",
    "question_contains_temporal_signal",
    "strip_temporal_context",
]
