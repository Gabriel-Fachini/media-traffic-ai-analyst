from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.core.router.classifier import classify_question
from app.core.router.date_resolution import apply_date_normalizer
from tests.fakes import FakeRouterRunnable


pytestmark = pytest.mark.eval

CASES_PATH = Path(__file__).with_name("router_cases.jsonl")
FIELD_THRESHOLDS = {
    "intent": 1.0,
    "needs_clarification": 1.0,
    "clarification_reason": 1.0,
    "refusal_reason": 1.0,
    "traffic_source": 1.0,
    "start_date": 1.0,
    "end_date": 1.0,
}


def _load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _coerce_expected_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def test_router_eval_matches_offline_thresholds() -> None:
    cases = _load_cases()
    scores = {field: [0, 0] for field in FIELD_THRESHOLDS}

    for case in cases:
        reference_date = date.fromisoformat(case["reference_date"])
        with patch("app.core.dates._resolve_reference_date", return_value=reference_date), patch(
            "tests.fakes._resolve_reference_date",
            return_value=reference_date,
        ):
            decision = classify_question(
                case["question"],
                _router_runnable=FakeRouterRunnable(),
            )
            decision = apply_date_normalizer(case["question"], decision)

        actual = {
            "intent": decision.intent,
            "needs_clarification": decision.needs_clarification,
            "clarification_reason": decision.clarification_reason,
            "refusal_reason": decision.refusal_reason,
            "traffic_source": decision.traffic_source,
            "start_date": decision.start_date,
            "end_date": decision.end_date,
        }
        expected = {
            "intent": case.get("expected_intent"),
            "needs_clarification": case.get("expected_needs_clarification"),
            "clarification_reason": case.get("expected_clarification_reason"),
            "refusal_reason": case.get("expected_refusal_reason"),
            "traffic_source": case.get("expected_traffic_source"),
            "start_date": _coerce_expected_date(case.get("expected_start_date")),
            "end_date": _coerce_expected_date(case.get("expected_end_date")),
        }

        for field in FIELD_THRESHOLDS:
            expected_value = expected[field]
            if expected_value is None:
                continue
            scores[field][1] += 1
            if actual[field] == expected_value:
                scores[field][0] += 1

    failures: list[str] = []
    for field, threshold in FIELD_THRESHOLDS.items():
        correct, total = scores[field]
        accuracy = correct / total if total else 1.0
        if accuracy < threshold:
            failures.append(
                f"{field}: accuracy {accuracy:.1%} abaixo do threshold {threshold:.1%} "
                f"({correct}/{total})"
            )

    assert not failures, "\n".join(failures)
