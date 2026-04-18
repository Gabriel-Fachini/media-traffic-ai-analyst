from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from app.graph import AnalyticsGraphState, invoke_analytics_graph
from app.utils.config import SettingsError


@dataclass(frozen=True)
class ValidationScenario:
    name: str
    description: str
    question: str


def build_scenarios() -> list[ValidationScenario]:
    return [
        ValidationScenario(
            name="traffic-volume-all",
            description="Valida sintese textual de volume agregado por canal.",
            question=(
                "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
            ),
        ),
        ValidationScenario(
            name="traffic-volume-search",
            description="Valida sintese textual de volume filtrado por Search.",
            question=(
                "Qual foi o volume de usuarios de Search entre 2024-01-01 e "
                "2024-01-31?"
            ),
        ),
        ValidationScenario(
            name="channel-performance-all",
            description="Valida sintese textual de ranking de receita por canal.",
            question=(
                "Quais canais tiveram melhor desempenho de receita entre "
                "2024-01-01 e 2024-01-31?"
            ),
        ),
        ValidationScenario(
            name="channel-performance-search",
            description="Valida sintese textual de receita e pedidos de Search.",
            question=(
                "Qual foi a receita e o total de pedidos de Search entre 2024-01-01 "
                "e 2024-01-31?"
            ),
        ),
        ValidationScenario(
            name="missing-dates",
            description="Valida pedido de clarificacao quando faltam datas.",
            question="Qual foi a receita de Search?",
        ),
        ValidationScenario(
            name="out-of-scope",
            description="Valida recusa educada para pergunta fora do dominio.",
            question="Como fazer um bolo?",
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa cenarios manuais de validacao das respostas do grafo."
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
    parser.add_argument(
        "--show-messages",
        action="store_true",
        help="Exibe o historico de mensagens retornado pelo grafo.",
    )
    parser.add_argument(
        "--show-tool-results",
        action="store_true",
        help=(
            "Exibe o payload bruto de ToolMessage. Quando omitido, o script mostra "
            "apenas a resposta final e as tools usadas."
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


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
                    continue
                parts.append(json.dumps(item, ensure_ascii=False, default=str))
                continue
            parts.append(str(item))
        return "\n".join(parts)

    return str(content)


def _format_tools_used(tools_used: list[str]) -> str:
    if not tools_used:
        return "nenhuma"
    return ", ".join(tools_used)


def _render_tool_calls(message: AIMessage) -> str:
    if not message.tool_calls:
        return ""

    return json.dumps(
        [
            {"name": tool_call["name"], "args": tool_call["args"]}
            for tool_call in message.tool_calls
        ],
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _extract_tool_payload(message: ToolMessage) -> str:
    artifact = getattr(message, "artifact", None)
    if isinstance(artifact, ToolMessage):
        return _content_to_text(artifact.content).strip()
    if artifact is not None:
        return json.dumps(artifact, ensure_ascii=False, indent=2, default=str)
    return _content_to_text(message.content).strip()


def _print_message_trace(
    messages: list[AnyMessage],
    *,
    show_tool_results: bool,
) -> None:
    print("Mensagens:")

    for index, message in enumerate(messages, start=1):
        if isinstance(message, HumanMessage):
            role = "HumanMessage"
        elif isinstance(message, ToolMessage):
            role = f"ToolMessage[{message.name or 'unknown'}]"
        elif isinstance(message, AIMessage):
            role = "AIMessage"
        else:
            role = message.__class__.__name__

        print(f"  [{index}] {role}")

        if isinstance(message, AIMessage) and message.tool_calls:
            print("    tool_calls:")
            print(_indent_block(_render_tool_calls(message), prefix="      "))

        if isinstance(message, ToolMessage) and not show_tool_results:
            status = message.status or "success"
            print(f"    status: {status}")
            print("    content: omitido; use --show-tool-results para inspecionar.")
            continue

        if isinstance(message, ToolMessage):
            content = _extract_tool_payload(message)
        else:
            content = _content_to_text(message.content).strip()

        if content:
            print(_indent_block(content, prefix="    "))
        else:
            print("    <sem conteudo textual>")


def _print_tool_results(messages: list[AnyMessage]) -> None:
    tool_messages = [
        message for message in messages if isinstance(message, ToolMessage)
    ]
    if not tool_messages:
        return

    print("Resultados brutos das tools:")
    for message in tool_messages:
        status = message.status or "success"
        print(f"  - {message.name or 'unknown'} (status={status})")
        payload = _extract_tool_payload(message)
        print(_indent_block(payload or "<vazio>", prefix="    "))


def _indent_block(content: str, *, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in content.splitlines())


def _print_state(
    scenario: ValidationScenario,
    state: AnalyticsGraphState,
    *,
    show_messages: bool,
    show_tool_results: bool,
) -> None:
    messages = cast(list[AnyMessage], state.get("messages", []))
    final_answer = state.get("final_answer", "").strip()
    tools_used = cast(list[str], state.get("tools_used", []))

    print(f"[RUN] {scenario.name}")
    print(f"Descricao: {scenario.description}")
    print(f"Pergunta: {scenario.question}")
    print(f"Tools usadas: {_format_tools_used(tools_used)}")
    print("Resposta final:")
    print(_indent_block(final_answer or "<vazia>", prefix="  "))

    if show_tool_results:
        _print_tool_results(messages)

    if show_messages:
        _print_message_trace(messages, show_tool_results=show_tool_results)

    print()


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
            state = invoke_analytics_graph(scenario.question)
            _print_state(
                scenario,
                state,
                show_messages=args.show_messages,
                show_tool_results=args.show_tool_results,
            )
    except SettingsError as exc:
        print(f"[ERRO] {exc}")
        return 1
    except Exception as exc:
        print(f"[ERRO] Falha ao executar o grafo: {exc}")
        return 1

    print(f"[OK] {len(selected_scenarios)} cenario(s) executado(s) com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
