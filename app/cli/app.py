from __future__ import annotations

from typing import Annotated

import httpx
import typer
from rich.text import Text

from app.cli.rendering import (
    CliSession,
    DEFAULT_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    _build_info_panel,
    _build_warning_panel,
    _render_prompt,
    _render_startup,
    console,
)
from app.cli.sse_client import (
    _resolve_stream_api_url,
    _submit_question,
)


def _handle_command(command: str, session: CliSession, api_url: str, *, debug: bool) -> bool:
    normalized = command.strip().lower()

    if normalized == "/help":
        from app.cli.rendering import _build_help_panel
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
        _render_startup(_resolve_stream_api_url(api_url), debug=debug)
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


def _run_chat_loop(*, api_url: str, timeout: float, debug: bool) -> None:
    session = CliSession()
    _render_startup(_resolve_stream_api_url(api_url), debug=debug)

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

            _submit_question(
                client,
                api_url=api_url,
                session=session,
                question=question,
                debug=debug,
            )
            console.print()


def main(
    api_url: Annotated[
        str,
        typer.Option(
            "--api-url",
            help="URL completa do endpoint /query ou /query/stream usado pela CLI.",
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
