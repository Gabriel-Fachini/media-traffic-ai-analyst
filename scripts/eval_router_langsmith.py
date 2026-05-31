"""Roda o eval do router como um experiment no LangSmith.

Mede o router LLM real de producao (`classify_question`), que e
nao-deterministico e por isso precisa de inspeccao de traces — exatamente o que
o LangSmith oferece.

Opt-in e gated por ambiente: so roda quando LangSmith estiver configurado
(`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` + `LANGCHAIN_PROJECT`) e um
provider LLM valido estiver disponivel. Sem isso, encerra com exit 0 (skip), sem
quebrar quem nao configurou.

Campos avaliados: apenas os que o LLM realmente decide — `intent`,
`needs_clarification`, `clarification_reason`, `refusal_reason`,
`traffic_source`. As datas (`start_date`/`end_date`) NAO entram aqui porque sao
normalizadas deterministicamente no `date_normalizer` (no `preprocess_node`,
depois do router) e ja sao cobertas pelo eval offline.

Semantica de `null` no dataset: campo de referencia `null` significa "nao
verificar" (paridade com o eval offline da Fase 0), nao "esperar None".

Uso:
    poetry run python scripts/eval_router_langsmith.py
    poetry run python scripts/eval_router_langsmith.py --recreate
    poetry run python scripts/eval_router_langsmith.py --dataset meu-dataset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from langsmith.evaluation import EvaluationResult, EvaluationResults

from app.graph.llm_router import classify_question
from app.infra.env import get_settings

CASES_PATH = Path(__file__).resolve().parent.parent / "tests" / "eval" / "router_cases.jsonl"
DEFAULT_DATASET_NAME = "router-cases"

# Campos decididos pelo LLM (datas ficam de fora — sao deterministicas).
LLM_FIELDS: tuple[str, ...] = (
    "intent",
    "needs_clarification",
    "clarification_reason",
    "refusal_reason",
    "traffic_source",
)


def load_cases() -> list[dict[str, Any]]:
    """Le o JSONL de casos (uma linha = um exemplo)."""
    cases: list[dict[str, Any]] = []
    with CASES_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _example_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return {"question": case["question"], "reference_date": case["reference_date"]}


def _example_outputs(case: dict[str, Any]) -> dict[str, Any]:
    """Referencia: so os campos que o LLM decide (mantem null = nao verificar)."""
    return {field: case.get(f"expected_{field}") for field in LLM_FIELDS}


def ensure_dataset(client: Any, name: str, *, recreate: bool) -> Any:
    """Cria/sincroniza o dataset no LangSmith de forma idempotente.

    - Se nao existe: cria e popula a partir do JSONL.
    - Se existe e `recreate=True`: apaga e recria (use quando o JSONL mudar).
    - Se existe e `recreate=False`: reusa como esta.
    """
    cases = load_cases()

    if client.has_dataset(dataset_name=name):
        if recreate:
            client.delete_dataset(dataset_name=name)
            print(f"Dataset '{name}' apagado para recriacao.")
        else:
            print(f"Dataset '{name}' ja existe — reusando (use --recreate para sincronizar).")
            return client.read_dataset(dataset_name=name)

    dataset = client.create_dataset(
        dataset_name=name,
        description="Casos do router (Fase 0) para avaliar o router LLM de producao.",
    )
    client.create_examples(
        inputs=[_example_inputs(c) for c in cases],
        outputs=[_example_outputs(c) for c in cases],
        metadata=[{"group": c["group"]} for c in cases],
        dataset_id=dataset.id,
    )
    print(f"Dataset '{name}' criado com {len(cases)} exemplos.")
    return dataset


def router_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Sistema sob teste: o router LLM real. So expoe os campos avaliados."""
    decision = classify_question(inputs["question"])
    return {
        "intent": decision.intent,
        "needs_clarification": decision.needs_clarification,
        "clarification_reason": decision.clarification_reason,
        "refusal_reason": decision.refusal_reason,
        "traffic_source": decision.normalized_params.traffic_source,
    }


def field_correctness(run: Any, example: Any) -> EvaluationResults:
    """Evaluator row-level: um score por campo do LLM.

    Retorna uma metrica por campo (`<campo>_correct`). Campo com referencia
    `null` recebe score `None` (N/A) — paridade com o eval offline.
    """
    actual = run.outputs or {}
    expected = example.outputs or {}
    results: list[EvaluationResult] = []
    for field in LLM_FIELDS:
        exp_val = expected.get(field)
        if exp_val is None:
            results.append(EvaluationResult(key=f"{field}_correct", score=None, comment="N/A"))
            continue
        act_val = actual.get(field)
        results.append(
            EvaluationResult(
                key=f"{field}_correct",
                score=int(act_val == exp_val),
                comment=f"esperado={exp_val!r} atual={act_val!r}",
            )
        )
    return EvaluationResults(results=results)


def overall_accuracy(runs: Sequence[Any], examples: Sequence[Any]) -> EvaluationResult:
    """Summary evaluator: accuracy agregada sobre todas as comparacoes validas."""
    total = 0
    correct = 0
    for run, example in zip(runs, examples):
        actual = run.outputs or {}
        expected = example.outputs or {}
        for field in LLM_FIELDS:
            exp_val = expected.get(field)
            if exp_val is None:
                continue
            total += 1
            if actual.get(field) == exp_val:
                correct += 1
    score = correct / total if total else 0.0
    return EvaluationResult(key="overall_field_accuracy", score=score)


def _langsmith_configured() -> bool:
    return (
        os.getenv("LANGCHAIN_TRACING_V2", "").strip().lower() == "true"
        and bool(os.getenv("LANGCHAIN_API_KEY", "").strip())
        and bool(os.getenv("LANGCHAIN_PROJECT", "").strip())
    )


def _result_has_failures(results: Any) -> bool:
    results.wait()
    summary_results = getattr(results, "_summary_results", {}) or {}
    for item in summary_results.get("results", []):
        if item.get("key") == "overall_field_accuracy" and (item.get("score") or 0) < 1.0:
            return True

    for row in results:
        for item in row.get("evaluation_results", {}).get("results", []):
            score = item.get("score")
            if score is not None and score < 1:
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET_NAME,
        help=f"Nome do dataset no LangSmith (default: {DEFAULT_DATASET_NAME}).",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Apaga e recria o dataset a partir do JSONL (use quando os casos mudarem).",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Chamadas LLM concorrentes (default: 4).",
    )
    args = parser.parse_args()

    if not _langsmith_configured():
        print(
            "LangSmith nao configurado. Defina LANGCHAIN_TRACING_V2=true, "
            "LANGCHAIN_API_KEY e LANGCHAIN_PROJECT no .env. Encerrando (skip).",
            file=sys.stderr,
        )
        return 0

    # Imports tardios: so quando o experiment vai mesmo rodar.
    from langsmith import Client, evaluate

    client = Client()
    ensure_dataset(client, args.dataset, recreate=args.recreate)

    results = evaluate(
        router_target,
        data=args.dataset,
        evaluators=[field_correctness],
        summary_evaluators=[overall_accuracy],
        experiment_prefix="router-llm",
        metadata={"router": "llm", "model": get_settings().llm_model},
        max_concurrency=args.max_concurrency,
    )

    print(f"\nExperiment concluido: {results.experiment_name}")
    print("Veja os traces e metricas no LangSmith.")
    return 1 if _result_has_failures(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
