"""Tests for _apply_date_normalizer — the bridge between LLM router and date normalizer.

The LLM router is instructed not to infer dates, so it leaves start_date/end_date null
for relative expressions. _apply_date_normalizer fills them in deterministically and
clears spurious missing_dates clarification requests.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.graph.workflow import _apply_date_normalizer
from app.schemas.router import RouterDecision, RouterIntent


pytestmark = pytest.mark.unit

_TODAY = date(2026, 4, 20)


def _llm_missing_dates_decision(
    intent: RouterIntent = "traffic_volume",
    traffic_source: str | None = "Search",
) -> RouterDecision:
    return RouterDecision(
        intent=intent,
        traffic_source=traffic_source,
        start_date=None,
        end_date=None,
        needs_clarification=True,
        clarification_reason="missing_dates",
        response_message="Preciso que voce informe o periodo.",
    )


@pytest.mark.parametrize(
    ("question", "expected_start", "expected_end"),
    [
        (
            "Qual foi o trafego de search no ultimo mes?",
            date(2026, 3, 1),
            date(2026, 3, 31),
        ),
        (
            "Quantos usuarios vieram do Facebook este mes?",
            date(2026, 4, 1),
            date(2026, 4, 20),
        ),
        (
            "Receita de Organic nos ultimos 7 dias",
            date(2026, 4, 14),
            date(2026, 4, 20),
        ),
        (
            "Trafego de Search ontem",
            date(2026, 4, 19),
            date(2026, 4, 19),
        ),
        (
            "Usuarios nos ultimos 30 dias",
            date(2026, 3, 22),
            date(2026, 4, 20),
        ),
    ],
)
def test_apply_date_normalizer_resolves_relative_period_and_clears_missing_dates(
    question: str,
    expected_start: date,
    expected_end: date,
) -> None:
    decision = _llm_missing_dates_decision()
    with patch("app.graph.date_normalizer.date") as mock_date:
        mock_date.today.return_value = _TODAY
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        result = _apply_date_normalizer(question, decision)

    assert result.needs_clarification is False
    assert result.clarification_reason is None
    assert result.response_message is None
    assert result.start_date == expected_start
    assert result.end_date == expected_end
    assert result.traffic_source == decision.traffic_source
    assert result.intent == decision.intent


def test_apply_date_normalizer_no_temporal_signal_preserves_missing_dates() -> None:
    question = "Qual foi o trafego de Search?"
    decision = _llm_missing_dates_decision()
    result = _apply_date_normalizer(question, decision)

    assert result.needs_clarification is True
    assert result.clarification_reason == "missing_dates"


def test_apply_date_normalizer_preserves_llm_resolved_dates() -> None:
    question = "Trafego de Search no ultimo mes"
    decision = RouterDecision(
        intent="traffic_volume",
        traffic_source="Search",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        needs_clarification=False,
    )
    result = _apply_date_normalizer(question, decision)

    assert result.start_date == date(2026, 3, 1)
    assert result.end_date == date(2026, 3, 31)
    assert result.needs_clarification is False


def test_apply_date_normalizer_preserves_non_missing_dates_clarification() -> None:
    question = "Trafego de Search no ultimo mes"
    decision = RouterDecision(
        intent="ambiguous_analytics",
        traffic_source="Search",
        needs_clarification=True,
        clarification_reason="ambiguous_metric",
        response_message="Voce quer volume ou receita?",
    )
    result = _apply_date_normalizer(question, decision)

    assert result.needs_clarification is True
    assert result.clarification_reason == "ambiguous_metric"
