"""
Eval harness para o router determinístico.

Cada caso do JSONL tem campos `expected_*`. Quando um campo é null, ele é
ignorado na comparação — útil para casos onde só queremos medir um subconjunto
dos atributos (ex: só datas, sem verificar intent).

Ao final, o test imprime accuracy por campo e falha se qualquer accuracy
ficar abaixo do threshold definido em FIELD_THRESHOLDS.

Marker: `eval` — rodar com `poetry run pytest -m eval`.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.deterministic_router import build_router_decision
from app.schemas.router import RouterDecision

CASES_PATH = Path(__file__).parent / "router_cases.jsonl"

# Accuracy mínima exigida por campo (0.0–1.0).
# Baseada no baseline do router determinístico — deve ser 1.0 para todos.
FIELD_THRESHOLDS: dict[str, float] = {
    "intent": 1.0,
    "needs_clarification": 1.0,
    "clarification_reason": 1.0,
    "refusal_reason": 1.0,
    "traffic_source": 1.0,
    "start_date": 1.0,
    "end_date": 1.0,
}

pytestmark = pytest.mark.eval


def _load_cases() -> list[dict[str, Any]]:
    cases = []
    with CASES_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _extract_actual(decision: RouterDecision) -> dict[str, Any]:
    return {
        "intent": decision.intent,
        "needs_clarification": decision.needs_clarification,
        "clarification_reason": decision.clarification_reason,
        "refusal_reason": decision.refusal_reason,
        "traffic_source": decision.normalized_params.traffic_source,
        "start_date": decision.normalized_params.start_date,
        "end_date": decision.normalized_params.end_date,
    }


def _parse_expected(case: dict[str, Any]) -> dict[str, Any]:
    """Converte strings de data para date e mantém null como None (skip)."""
    expected: dict[str, Any] = {}
    for field in ("intent", "needs_clarification", "clarification_reason", "refusal_reason", "traffic_source"):
        val = case.get(f"expected_{field}")
        expected[field] = val  # None significa "não verificar"
    for field in ("start_date", "end_date"):
        raw = case.get(f"expected_{field}")
        expected[field] = date.fromisoformat(raw) if raw else None
    return expected


def test_router_eval_accuracy() -> None:
    """Avalia o router em todos os casos e reporta accuracy por campo."""
    cases = _load_cases()
    assert cases, f"Nenhum caso encontrado em {CASES_PATH}"

    # Contadores: total avaliado e total correto, por campo
    totals: dict[str, int] = {f: 0 for f in FIELD_THRESHOLDS}
    correct: dict[str, int] = {f: 0 for f in FIELD_THRESHOLDS}
    failures: list[str] = []

    for case in cases:
        question = case["question"]
        ref_date = date.fromisoformat(case["reference_date"])
        expected = _parse_expected(case)
        decision = build_router_decision(question, reference_date=ref_date)
        actual = _extract_actual(decision)

        for field, exp_val in expected.items():
            if exp_val is None:
                continue  # campo marcado como "não verificar"
            totals[field] += 1
            act_val = actual[field]
            if act_val == exp_val:
                correct[field] += 1
            else:
                failures.append(
                    f"[{case['group']}] {field!r}: esperado={exp_val!r} atual={act_val!r} | pergunta={question!r}"
                )

    # Calcula accuracy e verifica thresholds
    print("\n--- Router Eval Accuracy ---")
    threshold_failures: list[str] = []
    for field, threshold in FIELD_THRESHOLDS.items():
        total = totals[field]
        if total == 0:
            print(f"  {field}: N/A (nenhum caso avaliado)")
            continue
        acc = correct[field] / total
        status = "OK" if acc >= threshold else "FAIL"
        print(f"  {field}: {correct[field]}/{total} = {acc:.1%} [{status}] (min={threshold:.0%})")
        if acc < threshold:
            threshold_failures.append(
                f"{field}: accuracy={acc:.1%} < threshold={threshold:.1%}"
            )

    if failures:
        print("\n--- Falhas por caso ---")
        for msg in failures:
            print(f"  {msg}")

    assert not threshold_failures, (
        "Accuracy abaixo do threshold em:\n" + "\n".join(threshold_failures)
    )
