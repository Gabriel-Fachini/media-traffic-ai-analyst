from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.schemas import DebugError, DebugInfo, ErrorResponse, QueryRequest, QueryResponse

DEFAULT_API_URL = "http://127.0.0.1:8000/query"
DEFAULT_TIMEOUT_SECONDS = 120.0

console = Console()


@dataclass
class CliSession:
    thread_id: str | None = None


def _build_banner(api_url: str) -> Panel:
    header = Text("Media Traffic AI Analyst", style="bold white")
    subtitle = Text("CLI conversacional polida via API", style="italic bright_black")
    endpoint = Text.assemble(
        ("Endpoint: ", "bright_black"),
        (api_url, "bold cyan"),
    )
    commands = Text.assemble(
        ("Comandos rapidos: ", "bright_black"),
        ("/help", "bold green"),
        ("  ", ""),
        ("/new", "bold green"),
        ("  ", ""),
        ("/clear", "bold green"),
        ("  ", ""),
        ("/exit", "bold green"),
    )

    return Panel(
        Group(header, subtitle, Text(""), endpoint, commands),
        border_style="cyan",
        padding=(1, 2),
        title="Terminal",
    )


def _build_debug_panel(message: str, *, title: str = "Debug") -> Panel:
    return Panel(message, border_style="magenta", title=title, padding=(0, 2))


def _build_help_panel() -> Panel:
    commands = Table.grid(padding=(0, 2))
    commands.add_column(style="bold green", no_wrap=True)
    commands.add_column(style="white")
    commands.add_row("/help", "Mostra os comandos e exemplos de uso.")
    commands.add_row("/new", "Inicia uma nova conversa e limpa o contexto atual.")
    commands.add_row("/clear", "Limpa a tela e preserva a conversa atual.")
    commands.add_row("/exit", "Encerra a sessao sem stack trace.")

    examples = Table.grid(padding=(0, 1))
    examples.add_column(style="italic cyan")
    examples.add_row(
        "Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"
    )
    examples.add_row(
        "Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"
    )
    examples.add_row("Compare Search e Organic entre 2024-01-01 e 2024-01-31.")

    hint = Text(
        "Quando a API pedir clarificacao, responda no proximo turno e a CLI "
        "reaproveitara o mesmo thread_id.",
        style="bright_black",
    )

    return Panel(
        Group(
            Text("Comandos", style="bold white"),
            commands,
            Text(""),
            Text("Exemplos", style="bold white"),
            examples,
            Text(""),
            hint,
        ),
        border_style="green",
        title="Ajuda",
        padding=(1, 2),
    )


def _build_info_panel(message: str, *, title: str = "Info") -> Panel:
    return Panel(message, border_style="blue", title=title, padding=(0, 2))


def _build_warning_panel(message: str, *, title: str = "Aviso") -> Panel:
    return Panel(message, border_style="yellow", title=title, padding=(0, 2))


def _build_error_panel(message: str, *, title: str = "Erro") -> Panel:
    return Panel(message, border_style="red", title=title, padding=(0, 2))


def _format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _format_debug_error(debug_error: DebugError) -> str:
    details: list[str] = [f"[{debug_error.source}]"]
    if debug_error.tool_name:
        details.append(f"tool={debug_error.tool_name}")
    if debug_error.error_type:
        details.append(f"type={debug_error.error_type}")
    details.append(debug_error.message)
    return " ".join(details)


def _format_debug_info(debug_info: DebugInfo) -> str:
    blocks: list[str] = []

    if debug_info.resolved_question:
        blocks.append(f"resolved_question:\n{debug_info.resolved_question}")

    if debug_info.router_decision is not None:
        blocks.append(
            "router_decision:\n"
            f"{_format_json(debug_info.router_decision)}"
        )

    if debug_info.errors:
        blocks.append(
            "errors:\n"
            + "\n".join(f"- {_format_debug_error(error)}" for error in debug_info.errors)
        )

    return "\n\n".join(blocks) or "Nenhum detalhe adicional retornado."


def _build_http_debug_message(
    *,
    payload: dict[str, Any],
    response: httpx.Response | None = None,
    debug_info: DebugInfo | None = None,
    exc: Exception | None = None,
) -> str:
    blocks = [f"request_payload:\n{_format_json(payload)}"]

    if response is not None:
        raw_body = response.text.strip() or "<empty>"
        blocks.append(f"status_code:\n{response.status_code}")
        blocks.append(f"response_body:\n{raw_body}")

    if exc is not None:
        blocks.append(f"exception_type:\n{type(exc).__name__}")
        blocks.append(f"exception:\n{exc}")

    if debug_info is not None:
        blocks.append(f"response_debug:\n{_format_debug_info(debug_info)}")

    return "\n\n".join(blocks)


def _format_tools_used(tools_used: list[str]) -> str:
    if not tools_used:
        return "nenhuma"
    return ", ".join(tools_used)


def _format_context_message_count(count: int | None) -> str:
    if count is None:
        return "n/d"
    suffix = "mensagem" if count == 1 else "mensagens"
    return f"{count} {suffix}"


def _build_response_panel(response: QueryResponse) -> Panel:
    metadata = response.metadata
    footer = Text.assemble(
        ("tools: ", "bright_black"),
        (_format_tools_used(response.tools_used), "bold green"),
        ("  |  ", "bright_black"),
        ("contexto: ", "bright_black"),
        (
            _format_context_message_count(
                metadata.context_message_count if metadata else None
            ),
            "bold cyan",
        ),
    )

    return Panel(
        Group(Markdown(response.answer), Text(""), footer),
        border_style="green",
        padding=(1, 2),
        title="Analista",
    )


def _extract_error_response(response: httpx.Response) -> tuple[str, DebugInfo | None]:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase, None

    try:
        error_response = ErrorResponse.model_validate(payload)
    except ValidationError:
        error_response = None
    else:
        return error_response.detail, error_response.debug

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip(), None

    return response.text.strip() or response.reason_phrase, None


def _render_startup(api_url: str, *, debug: bool) -> None:
    console.clear()
    console.print(_build_banner(api_url))
    if debug:
        console.print(
            _build_debug_panel(
                "Modo debug ativo. A CLI exibira payloads, status HTTP e erros internos retornados pela API.",
                title="Debug Ativo",
            )
        )
    console.print(
        Text(
            "Digite sua pergunta e pressione Enter. Use /help para exemplos.",
            style="bright_black",
        )
    )
    console.print()


def _render_prompt() -> str:
    return console.input("[bold cyan]voce[/bold cyan] [bright_black]>[/bright_black] ")


def _handle_command(command: str, session: CliSession, api_url: str, *, debug: bool) -> bool:
    normalized = command.strip().lower()

    if normalized == "/help":
        console.print(_build_help_panel())
        return True

    if normalized == "/new":
        session.thread_id = None
        console.print(
            _build_info_panel(
                "Nova conversa iniciada. O proximo envio criara um novo contexto.",
                title="Nova Conversa",
            )
        )
        return True

    if normalized == "/clear":
        _render_startup(api_url, debug=debug)
        if session.thread_id:
            console.print(
                _build_info_panel(
                    "Tela limpa. A conversa atual continua ativa neste terminal.",
                    title="Contexto Mantido",
                )
            )
        return True

    if normalized == "/exit":
        raise typer.Exit()

    if normalized.startswith("/"):
        console.print(
            _build_warning_panel(
                "Comando desconhecido. Use /help para ver os comandos disponiveis."
            )
        )
        return True

    return False


def _build_request(question: str, thread_id: str | None) -> dict[str, Any]:
    request = QueryRequest(question=question, thread_id=thread_id)
    return request.model_dump(exclude_none=True)


def _submit_question(
    client: httpx.Client,
    *,
    api_url: str,
    session: CliSession,
    question: str,
    debug: bool,
) -> QueryResponse | None:
    try:
        payload = _build_request(question, session.thread_id)
    except ValidationError as exc:
        console.print(
            _build_error_panel(
                "A pergunta informada nao atende ao formato esperado. "
                f"Detalhe: {exc}",
                title="Entrada Invalida",
            )
        )
        return None

    try:
        with console.status(
            "[bold green]Consultando o analista...[/bold green]",
            spinner="dots",
        ):
            headers = {"X-Debug": "true"} if debug else None
            response = client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        console.print(
            _build_error_panel(
                "Nao consegui conectar com a API local. Suba o servidor com "
                "`poetry run fastapi dev` e tente novamente.",
                title="API Offline",
            )
        )
        if debug:
            console.print(
                _build_debug_panel(
                    _build_http_debug_message(payload=payload, exc=exc),
                    title="Debug HTTP",
                )
            )
        return None
    except httpx.TimeoutException as exc:
        console.print(
            _build_error_panel(
                "A API demorou mais do que o esperado para responder. Tente "
                "novamente em instantes.",
                title="Timeout",
            )
        )
        if debug:
            console.print(
                _build_debug_panel(
                    _build_http_debug_message(payload=payload, exc=exc),
                    title="Debug HTTP",
                )
            )
        return None
    except httpx.HTTPStatusError as exc:
        message, debug_info = _extract_error_response(exc.response)
        title = (
            "Falha da API"
            if exc.response.status_code >= 500
            else f"HTTP {exc.response.status_code}"
        )
        console.print(_build_error_panel(message, title=title))
        if debug:
            console.print(
                _build_debug_panel(
                    _build_http_debug_message(
                        payload=payload,
                        response=exc.response,
                        debug_info=debug_info,
                    ),
                    title="Debug HTTP",
                )
            )
        return None
    except httpx.RequestError as exc:
        console.print(
            _build_error_panel(
                "Nao foi possivel concluir a requisicao para a API. "
                f"Detalhe: {exc}",
                title="Falha de Rede",
            )
        )
        if debug:
            console.print(
                _build_debug_panel(
                    _build_http_debug_message(payload=payload, exc=exc),
                    title="Debug HTTP",
                )
            )
        return None

    try:
        parsed_response = QueryResponse.model_validate(response.json())
    except ValidationError as exc:
        console.print(
            _build_error_panel(
                "A API respondeu com um payload fora do contrato esperado. "
                f"Detalhe: {exc}",
                title="Payload Invalido",
            )
        )
        return None

    if parsed_response.metadata and parsed_response.metadata.thread_id:
        session.thread_id = parsed_response.metadata.thread_id

    if debug and parsed_response.metadata and parsed_response.metadata.debug:
        console.print(
            _build_debug_panel(
                _format_debug_info(parsed_response.metadata.debug),
                title="Debug Execucao",
            )
        )

    return parsed_response


def _run_chat_loop(*, api_url: str, timeout: float, debug: bool) -> None:
    session = CliSession()
    _render_startup(api_url, debug=debug)

    with httpx.Client(timeout=timeout) as client:
        while True:
            try:
                question = _render_prompt().strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                console.print(Text("Sessao encerrada.", style="bright_black"))
                return

            if not question:
                continue

            try:
                command_handled = _handle_command(question, session, api_url, debug=debug)
            except typer.Exit:
                console.print(Text("Sessao encerrada.", style="bright_black"))
                return

            if command_handled:
                console.print()
                continue

            response = _submit_question(
                client,
                api_url=api_url,
                session=session,
                question=question,
                debug=debug,
            )
            if response is not None:
                console.print(_build_response_panel(response))
            console.print()


def main(
    api_url: Annotated[
        str,
        typer.Option(
            "--api-url",
            help="URL completa do endpoint /query usado pela CLI.",
        ),
    ] = DEFAULT_API_URL,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            min=1.0,
            help="Timeout total da requisicao HTTP em segundos.",
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="Exibe detalhes tecnicos da requisicao e dos erros retornados pela API.",
        ),
    ] = False,
) -> None:
    _run_chat_loop(api_url=api_url, timeout=timeout, debug=debug)


def entrypoint() -> None:
    typer.run(main)


if __name__ == "__main__":
    entrypoint()
