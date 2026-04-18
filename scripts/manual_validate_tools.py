from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from typing import Callable

from pydantic import BaseModel

from app.clients.bigquery_client import BigQueryClientError
from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput
from app.tools import channel_performance_analyzer, traffic_volume_analyzer


@dataclass(frozen=True)
class ValidationScenario:
    name: str
    description: str
    runner: Callable[[], BaseModel]


def build_scenarios() -> list[ValidationScenario]:
    january_start = date(2024, 1, 1)
    january_end = date(2024, 1, 31)

    return [
        ValidationScenario(
            name="traffic-volume-all",
            description="Volume de trafego sem filtro de canal.",
            runner=lambda: traffic_volume_analyzer(
                TrafficVolumeInput(
                    start_date=january_start,
                    end_date=january_end,
                )
            ),
        ),
        ValidationScenario(
            name="traffic-volume-search",
            description="Volume de trafego filtrando Search.",
            runner=lambda: traffic_volume_analyzer(
                TrafficVolumeInput(
                    traffic_source="Search",
                    start_date=january_start,
                    end_date=january_end,
                )
            ),
        ),
        ValidationScenario(
            name="channel-performance-all",
            description="Performance financeira sem filtro de canal.",
            runner=lambda: channel_performance_analyzer(
                ChannelPerformanceInput(
                    start_date=january_start,
                    end_date=january_end,
                )
            ),
        ),
        ValidationScenario(
            name="channel-performance-search",
            description="Performance financeira filtrando Search.",
            runner=lambda: channel_performance_analyzer(
                ChannelPerformanceInput(
                    traffic_source="Search",
                    start_date=january_start,
                    end_date=january_end,
                )
            ),
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa cenarios manuais de validacao das tools analytics."
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_names",
        help=(
            "Nome do cenario a executar. Pode ser informado mais de uma vez. "
            "Quando omitido, executa todos os cenarios."
        ),
    )
    return parser.parse_args()


def select_scenarios(
    all_scenarios: list[ValidationScenario],
    scenario_names: list[str] | None,
) -> list[ValidationScenario]:
    if not scenario_names:
        return all_scenarios

    scenario_map = {scenario.name: scenario for scenario in all_scenarios}
    selected: list[ValidationScenario] = []

    for name in scenario_names:
        scenario = scenario_map.get(name)
        if scenario is None:
            available = ", ".join(sorted(scenario_map))
            raise ValueError(
                f"Cenario invalido: {name}. Opcoes disponiveis: {available}"
            )
        selected.append(scenario)

    return selected


def main() -> int:
    args = parse_args()
    scenarios = build_scenarios()

    try:
        selected_scenarios = select_scenarios(scenarios, args.scenario_names)
    except ValueError as exc:
        print(f"[ERRO] {exc}")
        return 1

    try:
        for scenario in selected_scenarios:
            print(f"[RUN] {scenario.name}")
            print(f"Descricao: {scenario.description}")
            result = scenario.runner()
            print(result.model_dump_json(indent=2))
            print()
    except BigQueryClientError as exc:
        print(f"[ERRO] {exc}")
        return 1

    print(f"[OK] {len(selected_scenarios)} cenario(s) executado(s) com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
