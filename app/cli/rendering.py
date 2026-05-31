from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich._spinners import SPINNERS
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from app.api.schemas import DebugError, DebugInfo, QueryResponse

SPINNERS["symbols_3"] = {"frames": ["✶", "✸", "✹", "✺", "✹", "✷"], "interval": 180}

DEFAULT_API_URL = "http://127.0.0.1:8000/query/stream"
DEFAULT_TIMEOUT_SECONDS = 120.0

console = Console()


@dataclass
class CliSession:
    thread_id: str | None = None


def _build_banner(api_url: str) -> Panel:
    header = Text("Media Traffic AI Analyst", style="bold white")
    subtitle = Text(
        "CLI conversacional polida via API com streaming SSE",
        style="italic bright_black",
    )
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


def _format_agent_tool_call(index: int, call: Any) -> str:
    args_lines = "\n".join(
        f"    {k}: {v}" for k, v in (call.args or {}).items()
    )
    return f"  [{index + 1}] {call.tool_name}\n{args_lines}" if args_lines else f"  [{index + 1}] {call.tool_name}"


def _format_debug_info(debug_info: DebugInfo) -> str:
    blocks: list[str] = []

    if debug_info.resolved_question:
        blocks.append(f"resolved_question:\n{debug_info.resolved_question}")

    if debug_info.router_intent:
        intent_line = f"router_intent: {debug_info.router_intent}"
        if debug_info.router_short_circuit:
            intent_line += f"  →  short-circuit: {debug_info.router_short_circuit}"
        blocks.append(intent_line)

    if debug_info.agent_tool_calls:
        calls_lines = "\n".join(
            _format_agent_tool_call(i, call)
            for i, call in enumerate(debug_info.agent_tool_calls)
        )
        blocks.append(f"agent_tool_calls (LLM decidiu):\n{calls_lines}")

    if debug_info.errors:
        blocks.append(
            "errors:\n"
            + "\n".join(f"- {_format_debug_error(error)}" for error in debug_info.errors)
        )

    if debug_info.observability:
        observability = debug_info.observability
        token_usage = observability.token_usage
        tools_used = (
            ", ".join(observability.tools_used)
            if observability.tools_used
            else "nenhuma"
        )
        blocks.append(
            "observability:\n"
            f"latency_ms: {observability.latency_ms if observability.latency_ms is not None else 'n/d'}\n"
            f"llm_call_count: {observability.llm_call_count}\n"
            f"tool_call_count: {observability.tool_call_count}\n"
            f"tools_used: {tools_used}\n"
            f"token_usage: input={token_usage.input_tokens} output={token_usage.output_tokens} total={token_usage.total_tokens}"
        )

    return "\n\n".join(blocks) or "Nenhum detalhe adicional retornado."


def _build_http_debug_message(
    *,
    payload: dict[str, Any],
    response: Any = None,
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


_PHASE_LABELS: dict[str, str] = {
    "routing": "Analisando pergunta...",
    "querying": "Consultando dados...",
    "synthesizing": "Sintetizando resposta...",
}


def _build_spinner_panel(phase: str, *, active_tool: str | None = None) -> Panel:
    label = _PHASE_LABELS.get(phase, "Analisando...")
    if active_tool:
        label = f"Consultando BigQuery ({active_tool})..."
    return Panel(
        Group(
            Text(""),
            Spinner("symbols_3", text=Text(f"   {label}", style="bold white"), style="dodger_blue2"),
        ),
        border_style="cyan",
        padding=(1, 4),
        title="Analista",
    )


def _build_stream_panel(answer_text: str) -> Panel:
    footer = Text.assemble(
        ("stream: ", "bright_black"),
        ("ao vivo", "bold green"),
    )
    return Panel(
        Group(Text(answer_text), Text(""), footer),
        border_style="cyan",
        padding=(1, 2),
        title="Analista",
    )


def _animate_text(
    live: Live,
    text: str,
    *,
    panel_builder: Any | None = None,
    chars_per_step: int = 3,
    delay: float = 0.015,
) -> None:
    build: Any = panel_builder if panel_builder is not None else _build_stream_panel
    for i in range(0, len(text), chars_per_step):
        live.update(build(text[: i + chars_per_step]))
        time.sleep(delay)


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
