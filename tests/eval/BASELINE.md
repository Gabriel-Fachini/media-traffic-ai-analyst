# Router Eval — Baseline

Router: determinístico (`app/graph/router.py`) — regex + frozensets.
Dataset: `tests/eval/router_cases.jsonl` — 24 casos, 7 campos avaliados.
Data: 2026-05-29

## Resultados

| Campo                | Corretos | Total | Accuracy |
|----------------------|----------|-------|----------|
| intent               | 23       | 23    | 100.0%   |
| needs_clarification  | 24       | 24    | 100.0%   |
| clarification_reason | 2        | 2     | 100.0%   |
| refusal_reason       | 2        | 2     | 100.0%   |
| traffic_source       | 14       | 14    | 100.0%   |
| start_date           | 20       | 20    | 100.0%   |
| end_date             | 20       | 20    | 100.0%   |

## Thresholds de regressão (Fase 1+)

Definidos em `FIELD_THRESHOLDS` no runner (`test_router_eval.py`).
O LLM-router deve manter accuracy >= 100% em todos os campos para que o eval passe.
Se algum campo regredir, o threshold pode ser ajustado com justificativa explícita.
