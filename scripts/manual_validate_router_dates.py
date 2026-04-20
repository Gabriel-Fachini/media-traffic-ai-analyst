from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.graph.router import INVALID_DATES_MESSAGE, build_router_decision

REFERENCE_DATE = date(2026, 4, 20)


@dataclass(frozen=True)
class RouterDateScenario:
    name: str
    question: str
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    expects_invalid_dates: bool = False


def build_scenarios() -> list[RouterDateScenario]:
    return [
        RouterDateScenario(
            name="ultimo-mes",
            question="Qual foi a receita de Search no ultimo mes?",
            expected_start_date=date(2026, 3, 1),
            expected_end_date=date(2026, 3, 31),
        ),
        RouterDateScenario(
            name="este-mes",
            question="Qual foi a receita de Search este mes?",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 20),
        ),
        RouterDateScenario(
            name="ultimos-7-dias",
            question="Qual foi a receita de Search nos ultimos 7 dias?",
            expected_start_date=date(2026, 4, 14),
            expected_end_date=date(2026, 4, 20),
        ),
        RouterDateScenario(
            name="ontem",
            question="Qual foi a receita de Search ontem?",
            expected_start_date=date(2026, 4, 19),
            expected_end_date=date(2026, 4, 19),
        ),
        RouterDateScenario(
            name="ultimo-mes-com-do",
            question="Qual foi a receita do Search do ultimo mes?",
            expected_start_date=date(2026, 3, 1),
            expected_end_date=date(2026, 3, 31),
        ),
        RouterDateScenario(
            name="datas-brasileiras",
            question="Qual foi a receita de Search entre 01/04/2026 e 20/04/2026?",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 20),
        ),
        RouterDateScenario(
            name="datas-brasileiras-com-de",
            question="Qual foi a receita do Search de 01/04/26 a 20/04/26?",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 20),
        ),
        RouterDateScenario(
            name="datas-brasileiras-ano-curto",
            question="Qual foi a receita de Search entre 01/04/26 e 20/04/26?",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 20),
        ),
        RouterDateScenario(
            name="data-unica-brasileira-ano-curto",
            question="Qual foi a receita de Search em 01/04/26?",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 1),
        ),
        RouterDateScenario(
            name="data-brasileira-invalida",
            question="Qual foi a receita de Search em 31/02/2026?",
            expects_invalid_dates=True,
        ),
    ]


def _assert_valid_range(scenario: RouterDateScenario) -> None:
    decision = build_router_decision(
        scenario.question,
        reference_date=REFERENCE_DATE,
    )
    actual_start_date = decision.normalized_params.start_date
    actual_end_date = decision.normalized_params.end_date

    if decision.needs_clarification:
        raise AssertionError(
            f"{scenario.name}: nao deveria pedir clarificacao. "
            f"Recebido={decision.response_message!r}"
        )
    if decision.refusal_reason is not None:
        raise AssertionError(
            f"{scenario.name}: nao deveria recusar a pergunta. "
            f"Recebido={decision.refusal_reason!r}"
        )
    if actual_start_date != scenario.expected_start_date:
        raise AssertionError(
            f"{scenario.name}: start_date inesperada. "
            f"Esperado={scenario.expected_start_date}, recebido={actual_start_date}"
        )
    if actual_end_date != scenario.expected_end_date:
        raise AssertionError(
            f"{scenario.name}: end_date inesperada. "
            f"Esperado={scenario.expected_end_date}, recebido={actual_end_date}"
        )
    if actual_start_date is None or actual_end_date is None:
        raise AssertionError(
            f"{scenario.name}: o parser deveria ter resolvido um intervalo completo."
        )

    print(
        f"[OK] {scenario.name}: {actual_start_date.isoformat()} -> "
        f"{actual_end_date.isoformat()}"
    )


def _assert_invalid_dates(scenario: RouterDateScenario) -> None:
    decision = build_router_decision(
        scenario.question,
        reference_date=REFERENCE_DATE,
    )

    if not decision.needs_clarification:
        raise AssertionError(
            f"{scenario.name}: deveria pedir clarificacao por data invalida."
        )
    if decision.clarification_reason != "invalid_dates":
        raise AssertionError(
            f"{scenario.name}: clarification_reason inesperado. "
            f"Recebido={decision.clarification_reason!r}"
        )
    if decision.response_message != INVALID_DATES_MESSAGE:
        raise AssertionError(
            f"{scenario.name}: mensagem inesperada. "
            f"Recebido={decision.response_message!r}"
        )

    print(f"[OK] {scenario.name}: invalid_dates detectado corretamente")


def main() -> int:
    scenarios = build_scenarios()

    for scenario in scenarios:
        if scenario.expects_invalid_dates:
            _assert_invalid_dates(scenario)
            continue

        _assert_valid_range(scenario)

    print(f"[OK] {len(scenarios)} cenario(s) de parsing temporal validados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
