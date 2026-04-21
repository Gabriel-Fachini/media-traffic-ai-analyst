from __future__ import annotations

from datetime import date

import pytest

from app.graph.router import INVALID_DATES_MESSAGE, build_router_decision


pytestmark = pytest.mark.unit

REFERENCE_DATE = date(2026, 4, 20)


@pytest.mark.parametrize(
    ("question", "expected_start_date", "expected_end_date"),
    [
        (
            "Qual foi a receita de Search no ultimo mes?",
            date(2026, 3, 1),
            date(2026, 3, 31),
        ),
        (
            "Qual foi a receita de Search este mes?",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Qual foi a receita de Search nos ultimos 7 dias?",
            date(2026, 4, 14),
            date(2026, 4, 20),
        ),
        (
            "Qual foi a receita de Search ontem?",
            date(2026, 4, 19),
            date(2026, 4, 19),
        ),
        (
            "Qual foi a receita do Search do ultimo mes?",
            date(2026, 3, 1),
            date(2026, 3, 31),
        ),
        (
            "Qual foi a receita de Search entre 01/04/2026 e 20/04/2026?",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Qual foi a receita do Search de 01/04/26 a 20/04/26?",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Qual foi a receita de Search entre 01/04/26 e 20/04/26?",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Qual foi a receita de Search em 01/04/26?",
            date(2026, 4, 1),
            date(2026, 4, 1),
        ),
    ],
)
def test_router_resolves_supported_date_formats(
    question: str,
    expected_start_date: date,
    expected_end_date: date,
) -> None:
    decision = build_router_decision(question, reference_date=REFERENCE_DATE)

    assert decision.needs_clarification is False
    assert decision.refusal_reason is None
    assert decision.normalized_params.start_date == expected_start_date
    assert decision.normalized_params.end_date == expected_end_date


def test_router_prioritizes_invalid_dates_when_detected() -> None:
    decision = build_router_decision(
        "Qual foi a receita de Search em 31/02/2026?",
        reference_date=REFERENCE_DATE,
    )

    assert decision.needs_clarification is True
    assert decision.clarification_reason == "invalid_dates"
    assert decision.response_message == INVALID_DATES_MESSAGE


@pytest.mark.parametrize(
    (
        "question",
        "expected_intent",
        "expected_clarification_reason",
        "expected_traffic_source",
        "expected_start_date",
        "expected_end_date",
        "expected_message_fragment",
    ),
    [
        (
            "Quanto vendeu Search ontem?",
            "channel_performance",
            None,
            "Search",
            date(2026, 4, 19),
            date(2026, 4, 19),
            None,
        ),
        (
            "Quanto vendeu Search em 01/04/26?",
            "channel_performance",
            None,
            "Search",
            date(2026, 4, 1),
            date(2026, 4, 1),
            None,
        ),
        (
            "Como o Search performou ontem?",
            "ambiguous_analytics",
            None,
            "Search",
            date(2026, 4, 19),
            date(2026, 4, 19),
            None,
        ),
        (
            "Me mostre Search ontem.",
            "ambiguous_analytics",
            None,
            "Search",
            date(2026, 4, 19),
            date(2026, 4, 19),
            None,
        ),
        (
            "Quais canais foram melhores ontem?",
            "ambiguous_analytics",
            None,
            None,
            date(2026, 4, 19),
            date(2026, 4, 19),
            None,
        ),
        (
            "Como o Search performou em 31/02/2026?",
            "ambiguous_analytics",
            "invalid_dates",
            "Search",
            None,
            None,
            None,
        ),
        (
            "Usuarios nos ultimos 7 dias",
            "traffic_volume",
            None,
            None,
            date(2026, 4, 14),
            date(2026, 4, 20),
            None,
        ),
        (
            "Usuarios ontem",
            "traffic_volume",
            None,
            None,
            date(2026, 4, 19),
            date(2026, 4, 19),
            None,
        ),
    ],
)
def test_router_resolves_semantic_scenarios(
    question: str,
    expected_intent: str,
    expected_clarification_reason: str | None,
    expected_traffic_source: str | None,
    expected_start_date: date | None,
    expected_end_date: date | None,
    expected_message_fragment: str | None,
) -> None:
    decision = build_router_decision(question, reference_date=REFERENCE_DATE)

    assert decision.intent == expected_intent
    assert decision.clarification_reason == expected_clarification_reason
    assert decision.normalized_params.traffic_source == expected_traffic_source
    assert decision.normalized_params.start_date == expected_start_date
    assert decision.normalized_params.end_date == expected_end_date
    if expected_message_fragment is not None:
        assert decision.response_message is not None
        assert expected_message_fragment in decision.response_message


@pytest.mark.parametrize(
    (
        "question",
        "expected_intent",
        "expected_clarification_reason",
        "expected_start_date",
        "expected_end_date",
    ),
    [
        (
            "Receita por canal entre 2024-01-01 e 2024-03-31",
            "channel_performance",
            None,
            date(2024, 1, 1),
            date(2024, 3, 31),
        ),
        (
            "Receita por canal no ultimo mes",
            "channel_performance",
            None,
            date(2026, 3, 1),
            date(2026, 3, 31),
        ),
        (
            "Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-03-31? E por que?",
            "channel_performance",
            None,
            date(2024, 1, 1),
            date(2024, 3, 31),
        ),
        (
            "Por que Organic ficou abaixo de Search entre 2024-01-01 e 2024-03-31?",
            "ambiguous_analytics",
            None,
            date(2024, 1, 1),
            date(2024, 3, 31),
        ),
    ],
)
def test_router_avoids_false_unsupported_dimension_refusals(
    question: str,
    expected_intent: str,
    expected_clarification_reason: str | None,
    expected_start_date: date,
    expected_end_date: date,
) -> None:
    decision = build_router_decision(question, reference_date=REFERENCE_DATE)

    assert decision.intent == expected_intent
    assert decision.refusal_reason is None
    assert decision.clarification_reason == expected_clarification_reason
    assert decision.normalized_params.start_date == expected_start_date
    assert decision.normalized_params.end_date == expected_end_date


def test_router_keeps_unsupported_dimension_for_real_dimension_request() -> None:
    decision = build_router_decision(
        "Qual foi a receita por campanha entre 2024-01-01 e 2024-01-31?",
        reference_date=REFERENCE_DATE,
    )

    assert decision.intent == "out_of_scope"
    assert decision.refusal_reason == "unsupported_dimension"


def test_router_keeps_unsupported_dimension_for_campaign_question_without_por() -> None:
    decision = build_router_decision(
        "Qual campanha deu mais lucro no Facebook ontem?",
        reference_date=REFERENCE_DATE,
    )

    assert decision.intent == "out_of_scope"
    assert decision.refusal_reason == "unsupported_dimension"
