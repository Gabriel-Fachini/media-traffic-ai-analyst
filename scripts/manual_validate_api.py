from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from fastapi.testclient import TestClient

from app.graph.llm import LlmTimeoutError
from app.main import LLM_TIMEOUT_ERROR_MESSAGE, app, get_query_graph
from app.schemas.api import QueryResponse
from app.graph.workflow import MISSING_DATES_MESSAGE


ScenarioRunner = Callable[[TestClient], None]


@dataclass(frozen=True)
class ValidationScenario:
    name: str
    description: str
    runner: ScenarioRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa cenarios manuais de validacao da Fase 4 da API."
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
        "--show-body",
        action="store_true",
        help="Mantido por compatibilidade. O script agora e verboso por padrao.",
    )
    return parser.parse_args()


def build_scenarios(*, show_body: bool) -> list[ValidationScenario]:
    return [
        ValidationScenario(
            name="health",
            description="Valida que o endpoint /health responde 200 com status basico.",
            runner=lambda client: run_health_check(client, show_body=show_body),
        ),
        ValidationScenario(
            name="query-traffic-volume",
            description="Valida /query com analise de volume de usuarios por canal.",
            runner=lambda client: run_query_traffic_volume(client, show_body=show_body),
        ),
        ValidationScenario(
            name="query-channel-performance",
            description="Valida /query com analise financeira por canal.",
            runner=lambda client: run_query_channel_performance(
                client,
                show_body=show_body,
            ),
        ),
        ValidationScenario(
            name="missing-dates",
            description="Valida clarificacao quando faltam datas na pergunta.",
            runner=lambda client: run_missing_dates(client, show_body=show_body),
        ),
        ValidationScenario(
            name="thread-continuity",
            description="Valida persistencia basica de contexto via thread_id.",
            runner=lambda client: run_thread_continuity(client, show_body=show_body),
        ),
        ValidationScenario(
            name="llm-timeout",
            description="Valida resposta HTTP 500 estruturada em timeout do LLM.",
            runner=lambda client: run_llm_timeout(client, show_body=show_body),
        ),
    ]


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


def print_response(response: Any) -> None:
    print(json.dumps(response.json(), ensure_ascii=False, indent=2, default=str))


def print_divider() -> None:
    print("-" * 80)


def print_step(title: str) -> None:
    print(f"[STEP] {title}")


def print_check(message: str) -> None:
    print(f"  [CHECK] {message}")


def print_request(method: str, path: str, payload: dict[str, Any] | None = None) -> None:
    print(f"  [HTTP] {method} {path}")
    if payload is None:
        print("  [HTTP] request body: <vazio>")
        return

    print("  [HTTP] request body:")
    print(_indent_block(_to_pretty_json(payload), prefix="    "))


def print_http_response(response: Any) -> None:
    print(f"  [HTTP] response status: {response.status_code}")
    print("  [HTTP] response body:")
    print(_indent_block(_to_pretty_json(response.json()), prefix="    "))


def _to_pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _indent_block(content: str, *, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in content.splitlines())


def assert_status_code(response: Any, expected_status_code: int) -> None:
    if response.status_code != expected_status_code:
        raise AssertionError(
            "Status code inesperado. "
            f"Esperado={expected_status_code}, recebido={response.status_code}, "
            f"body={response.text}"
        )


def parse_query_response(response: Any) -> QueryResponse:
    return QueryResponse.model_validate(response.json())


def run_health_check(client: TestClient, *, show_body: bool) -> None:
    del show_body
    print_step("Chamando endpoint de health")
    print_request("GET", "/health")
    response = client.get("/health")
    print_http_response(response)
    assert_status_code(response, 200)
    print_check("status code 200 confirmado")

    body = response.json()
    if body.get("status") != "ok":
        raise AssertionError(f"Payload inesperado em /health: {body}")
    print_check("payload contem status=ok")


def run_query_traffic_volume(client: TestClient, *, show_body: bool) -> None:
    del show_body
    payload = {
        "question": "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
    }
    print_step("Chamando /query para volume de trafego")
    print_request("POST", "/query", payload)
    response = client.post("/query", json=payload)
    print_http_response(response)
    assert_status_code(response, 200)
    print_check("status code 200 confirmado")
    body = parse_query_response(response)

    if "traffic_volume_analyzer" not in body.tools_used:
        raise AssertionError(
            f"Esperava traffic_volume_analyzer em tools_used, recebi {body.tools_used}"
        )
    print_check("traffic_volume_analyzer apareceu em tools_used")
    if not body.answer.strip():
        raise AssertionError("A resposta final veio vazia para traffic volume.")
    print_check("answer retornou texto nao vazio")
    if body.metadata is None or not body.metadata.thread_id:
        raise AssertionError("Metadata/thread_id ausente na resposta da API.")
    print_check(f"metadata.thread_id presente: {body.metadata.thread_id}")
    print_check(
        "context_message_count="
        f"{body.metadata.context_message_count} e thread_id_source="
        f"{body.metadata.thread_id_source}"
    )


def run_query_channel_performance(client: TestClient, *, show_body: bool) -> None:
    del show_body
    payload = {
        "question": (
            "Quais canais tiveram melhor desempenho de receita entre "
            "2024-01-01 e 2024-01-31?"
        )
    }
    print_step("Chamando /query para performance financeira")
    print_request("POST", "/query", payload)
    response = client.post("/query", json=payload)
    print_http_response(response)
    assert_status_code(response, 200)
    print_check("status code 200 confirmado")
    body = parse_query_response(response)

    if "channel_performance_analyzer" not in body.tools_used:
        raise AssertionError(
            "Esperava channel_performance_analyzer em tools_used, "
            f"recebi {body.tools_used}"
        )
    print_check("channel_performance_analyzer apareceu em tools_used")
    if not body.answer.strip():
        raise AssertionError("A resposta final veio vazia para channel performance.")
    print_check("answer retornou texto nao vazio")
    if body.metadata is None or not body.metadata.thread_id:
        raise AssertionError("Metadata/thread_id ausente na resposta da API.")
    print_check(f"metadata.thread_id presente: {body.metadata.thread_id}")
    print_check(
        "context_message_count="
        f"{body.metadata.context_message_count} e thread_id_source="
        f"{body.metadata.thread_id_source}"
    )


def run_missing_dates(client: TestClient, *, show_body: bool) -> None:
    del show_body
    payload = {"question": "Qual foi a receita de Search?"}
    print_step("Chamando /query sem datas para validar clarificacao")
    print_request("POST", "/query", payload)
    response = client.post("/query", json=payload)
    print_http_response(response)
    assert_status_code(response, 200)
    print_check("status code 200 confirmado")
    body = parse_query_response(response)

    if body.answer != MISSING_DATES_MESSAGE:
        raise AssertionError(
            "A API nao retornou a mensagem esperada de clarificacao. "
            f"Recebido={body.answer!r}"
        )
    print_check("mensagem de clarificacao de datas bateu com o esperado")
    if body.tools_used:
        raise AssertionError(
            "Nenhuma tool deveria ter sido usada quando faltam datas. "
            f"Recebido={body.tools_used}"
        )
    print_check("tools_used veio vazio, como esperado")


def run_thread_continuity(client: TestClient, *, show_body: bool) -> None:
    del show_body
    thread_id = f"api-validation-{uuid4()}"
    first_payload = {
        "thread_id": thread_id,
        "question": "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?",
    }
    print_step("Primeira chamada com thread_id fixo")
    print_request("POST", "/query", first_payload)
    first_response = client.post("/query", json=first_payload)
    print_http_response(first_response)
    assert_status_code(first_response, 200)
    print_check("primeira chamada respondeu 200")
    first_body = parse_query_response(first_response)

    second_payload = {
        "thread_id": thread_id,
        "question": (
            "Quais canais tiveram melhor desempenho de receita entre "
            "2024-01-01 e 2024-01-31?"
        ),
    }
    print_step("Segunda chamada reutilizando o mesmo thread_id")
    print_request("POST", "/query", second_payload)
    second_response = client.post("/query", json=second_payload)
    print_http_response(second_response)
    assert_status_code(second_response, 200)
    print_check("segunda chamada respondeu 200")
    second_body = parse_query_response(second_response)

    if first_body.metadata is None or second_body.metadata is None:
        raise AssertionError("Metadata ausente ao validar thread continuity.")
    if first_body.metadata.thread_id != thread_id:
        raise AssertionError("A primeira chamada nao preservou o thread_id informado.")
    print_check("primeira chamada preservou o thread_id informado")
    if second_body.metadata.thread_id != thread_id:
        raise AssertionError("A segunda chamada nao preservou o thread_id informado.")
    print_check("segunda chamada preservou o thread_id informado")
    if second_body.metadata.context_message_count <= first_body.metadata.context_message_count:
        raise AssertionError(
            "O contexto nao cresceu entre chamadas com o mesmo thread_id. "
            f"Primeira={first_body.metadata.context_message_count}, "
            f"segunda={second_body.metadata.context_message_count}"
        )
    print_check(
        "contexto cresceu entre chamadas: "
        f"{first_body.metadata.context_message_count} -> "
        f"{second_body.metadata.context_message_count}"
    )


def run_llm_timeout(client: TestClient, *, show_body: bool) -> None:
    del show_body
    original_overrides = dict(app.dependency_overrides)

    def fake_graph() -> Any:
        class FakeGraph:
            def invoke(
                self,
                state: dict[str, Any],
                config: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                del state, config
                raise LlmTimeoutError("simulated timeout")

        return FakeGraph()

    app.dependency_overrides[get_query_graph] = fake_graph

    try:
        payload = {
            "question": (
                "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
            )
        }
        print_step("Sobrescrevendo o grafo para simular timeout do LLM")
        print_request("POST", "/query", payload)
        response = client.post("/query", json=payload)
    finally:
        app.dependency_overrides = original_overrides

    print_http_response(response)
    assert_status_code(response, 500)
    print_check("status code 500 confirmado")
    body = response.json()

    if body.get("detail") != LLM_TIMEOUT_ERROR_MESSAGE:
        raise AssertionError(
            "A API nao retornou a mensagem esperada para timeout de LLM. "
            f"Recebido={body}"
        )
    print_check("payload de erro do timeout bateu com o esperado")


def main() -> int:
    args = parse_args()
    scenarios = build_scenarios(show_body=args.show_body)

    try:
        selected_scenarios = select_scenarios(scenarios, args.scenario_names)
    except ValueError as exc:
        print(f"[ERRO] {exc}")
        return 1

    client = TestClient(app, raise_server_exceptions=False)

    try:
        for scenario in selected_scenarios:
            print_divider()
            print(f"[RUN] {scenario.name}")
            print(f"Descricao: {scenario.description}")
            scenario.runner(client)
            print("[OK] Cenario validado com sucesso.")
            print()
    except AssertionError as exc:
        print(f"[ERRO] {exc}")
        return 1
    except Exception as exc:
        print(f"[ERRO] Falha inesperada durante a validacao da API: {exc}")
        return 1

    print_divider()
    print(f"[OK] {len(selected_scenarios)} cenario(s) executado(s) com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
