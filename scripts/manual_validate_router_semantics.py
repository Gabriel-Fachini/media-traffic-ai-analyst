from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.graph.router import build_router_decision

REFERENCE_DATE = date(2026, 4, 20)


@dataclass(frozen=True)
class RouterSemanticScenario:
    name: str
    question: str
    expected_intent: str
    expected_clarification_reason: str | None = None
    expected_refusal_reason: str | None = None
    expected_traffic_source: str | None = None
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    expected_message_fragment: str | None = None


def build_scenarios() -> list[RouterSemanticScenario]:
    return [
        RouterSemanticScenario(
            name="sales-alias-direct",
            question="Quanto vendeu Search ontem?",
            expected_intent="channel_performance",
            expected_traffic_source="Search",
            expected_start_date=date(2026, 4, 19),
            expected_end_date=date(2026, 4, 19),
        ),
        RouterSemanticScenario(
            name="financial-alias-short-year",
            question="Quanto vendeu Search em 01/04/26?",
            expected_intent="channel_performance",
            expected_traffic_source="Search",
            expected_start_date=date(2026, 4, 1),
            expected_end_date=date(2026, 4, 1),
        ),
        RouterSemanticScenario(
            name="guided-clarification-performed",
            question="Como o Search performou ontem?",
            expected_intent="ambiguous_analytics",
            expected_clarification_reason="ambiguous_metric",
            expected_traffic_source="Search",
            expected_start_date=date(2026, 4, 19),
            expected_end_date=date(2026, 4, 19),
            expected_message_fragment="volume de usuarios ou performance financeira",
        ),
        RouterSemanticScenario(
            name="guided-clarification-show-me",
            question="Me mostre Search ontem.",
            expected_intent="ambiguous_analytics",
            expected_clarification_reason="ambiguous_metric",
            expected_traffic_source="Search",
            expected_start_date=date(2026, 4, 19),
            expected_end_date=date(2026, 4, 19),
            expected_message_fragment="volume de usuarios ou performance financeira",
        ),
        RouterSemanticScenario(
            name="guided-clarification-best-channels",
            question="Quais canais foram melhores ontem?",
            expected_intent="ambiguous_analytics",
            expected_clarification_reason="ambiguous_metric",
            expected_start_date=date(2026, 4, 19),
            expected_end_date=date(2026, 4, 19),
            expected_message_fragment="os canais",
        ),
    ]


def main() -> int:
    scenarios = build_scenarios()

    for scenario in scenarios:
        decision = build_router_decision(
            scenario.question,
            reference_date=REFERENCE_DATE,
        )

        if decision.intent != scenario.expected_intent:
            raise AssertionError(
                f"{scenario.name}: intent inesperada. "
                f"Esperado={scenario.expected_intent}, recebido={decision.intent}"
            )
        if decision.clarification_reason != scenario.expected_clarification_reason:
            raise AssertionError(
                f"{scenario.name}: clarification_reason inesperado. "
                "Esperado="
                f"{scenario.expected_clarification_reason}, recebido="
                f"{decision.clarification_reason}"
            )
        if decision.refusal_reason != scenario.expected_refusal_reason:
            raise AssertionError(
                f"{scenario.name}: refusal_reason inesperado. "
                f"Esperado={scenario.expected_refusal_reason}, recebido={decision.refusal_reason}"
            )
        if (
            decision.normalized_params.traffic_source
            != scenario.expected_traffic_source
        ):
            raise AssertionError(
                f"{scenario.name}: traffic_source inesperado. "
                f"Esperado={scenario.expected_traffic_source}, recebido="
                f"{decision.normalized_params.traffic_source}"
            )
        if decision.normalized_params.start_date != scenario.expected_start_date:
            raise AssertionError(
                f"{scenario.name}: start_date inesperada. "
                f"Esperado={scenario.expected_start_date}, recebido="
                f"{decision.normalized_params.start_date}"
            )
        if decision.normalized_params.end_date != scenario.expected_end_date:
            raise AssertionError(
                f"{scenario.name}: end_date inesperada. "
                f"Esperado={scenario.expected_end_date}, recebido="
                f"{decision.normalized_params.end_date}"
            )
        if scenario.expected_message_fragment and (
            decision.response_message is None
            or scenario.expected_message_fragment not in decision.response_message
        ):
            raise AssertionError(
                f"{scenario.name}: mensagem nao contem o trecho esperado. "
                f"Trecho={scenario.expected_message_fragment!r}, recebido="
                f"{decision.response_message!r}"
            )

        print(
            f"[OK] {scenario.name}: intent={decision.intent}, "
            f"clarification={decision.clarification_reason}, "
            f"params={decision.normalized_params.model_dump(mode='json')}"
        )

    print(f"[OK] {len(scenarios)} cenario(s) semanticos validados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
