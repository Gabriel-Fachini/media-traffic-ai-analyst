from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

import httpx
from pydantic import ValidationError
from rich.text import Text

from app.api.schemas import ErrorResponse, QueryRequest, QueryResponse
from app.cli.rendering import (
    CliSession,
    _animate_text,
    _build_debug_panel,
    _build_error_panel,
    _build_http_debug_message,
    _build_response_panel,
    _build_spinner_panel,
    _build_stream_panel,
    _format_debug_info,
    console,
)
from rich.live import Live


def _resolve_stream_api_url(api_url: str) -> str:
    normalized = api_url.rstrip("/")
    if normalized.endswith("/query/stream"):
        return normalized
    if normalized.endswith("/query"):
        return f"{normalized}/stream"
    return normalized


def _build_request(question: str, thread_id: str | None) -> dict[str, Any]:
    request = QueryRequest(question=question, thread_id=thread_id)
    return request.model_dump(exclude_none=True)


def _iter_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, Any]]:
    event_name: str | None = None
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.strip("\r")
        if not line:
            if event_name is not None:
                payload = json.loads("\n".join(data_lines)) if data_lines else None
                yield event_name, payload
            event_name = None
            data_lines = []
            continue

        if line.startswith("event: "):
            event_name = line.removeprefix("event: ").strip()
            continue

        if line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))

    if event_name is not None:
        payload = json.loads("\n".join(data_lines)) if data_lines else None
        yield event_name, payload


def _extract_error_response(response: httpx.Response) -> tuple[str, ErrorResponse | None]:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase, None

    try:
        error_response = ErrorResponse.model_validate(payload)
    except ValidationError:
        error_response = None
    else:
        return error_response.detail, error_response

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip(), None

    return response.text.strip() or response.reason_phrase, None


def _submit_question(
    client: httpx.Client,
    *,
    api_url: str,
    session: CliSession,
    question: str,
    debug: bool,
) -> QueryResponse | None:
    stream_api_url = _resolve_stream_api_url(api_url)
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
        headers = {"X-Debug": "true"} if debug else None
        with client.stream(
            "POST",
            stream_api_url,
            json=payload,
            headers=headers,
        ) as response:
            if response.is_error:
                message, error_obj = _extract_error_response(response)
                debug_info = error_obj.debug if error_obj else None
                title = (
                    "Falha da API"
                    if response.status_code >= 500
                    else f"HTTP {response.status_code}"
                )
                console.print(_build_error_panel(message, title=title))
                if debug:
                    console.print(
                        _build_debug_panel(
                            _build_http_debug_message(
                                payload=payload,
                                response=response,
                                debug_info=debug_info,
                            ),
                            title="Debug HTTP",
                        )
                    )
                return None

            phase = "routing"
            current_answer = ""
            active_tool: str | None = None
            error_response: ErrorResponse | None = None
            final_response: QueryResponse | None = None

            with Live(
                _build_spinner_panel(phase),
                console=console,
                refresh_per_second=12,
            ) as live:
                for event_name, event_payload in _iter_sse_events(response.iter_lines()):
                    if event_name == "metadata" and isinstance(event_payload, dict):
                        thread_id = event_payload.get("thread_id")
                        if isinstance(thread_id, str) and thread_id.strip():
                            session.thread_id = thread_id.strip()
                        continue

                    if event_name == "router":
                        live.console.print(
                            Text("  ✓  Pergunta analisada", style="bold green")
                        )
                        phase = "querying"
                        live.update(_build_spinner_panel(phase))
                        continue

                    if event_name == "tool_start" and isinstance(event_payload, dict):
                        tool_name = event_payload.get("tool_name")
                        active_tool = (
                            tool_name.strip()
                            if isinstance(tool_name, str) and tool_name.strip()
                            else None
                        )
                        phase = "querying"
                        live.update(_build_spinner_panel(phase, active_tool=active_tool))
                        continue

                    if event_name == "tool_end":
                        if active_tool:
                            live.console.print(
                                Text(f"  ✓  {active_tool} chamado", style="bold green")
                            )
                        active_tool = None
                        phase = "synthesizing"
                        live.update(_build_spinner_panel(phase))
                        continue

                    if event_name == "token" and isinstance(event_payload, dict):
                        text_delta = event_payload.get("text_delta")
                        text = event_payload.get("text")
                        if isinstance(text_delta, str):
                            current_answer += text_delta
                            phase = "streaming"
                            live.update(_build_stream_panel(current_answer))
                            continue
                        if isinstance(text, str):
                            current_answer = text
                            phase = "streaming"
                            live.update(_build_stream_panel(current_answer))
                        continue

                    if event_name == "final":
                        try:
                            final_response = QueryResponse.model_validate(event_payload)
                        except ValidationError as exc:
                            console.print(
                                _build_error_panel(
                                    "A API respondeu com um evento final fora do contrato esperado. "
                                    f"Detalhe: {exc}",
                                    title="Payload Invalido",
                                )
                            )
                            return None

                        if final_response.metadata and final_response.metadata.thread_id:
                            session.thread_id = final_response.metadata.thread_id

                        if not current_answer and final_response.answer:
                            _animate_text(live, final_response.answer)

                        live.update(_build_response_panel(final_response))
                        continue

                    if event_name == "error":
                        try:
                            error_response = ErrorResponse.model_validate(event_payload)
                        except ValidationError as exc:
                            console.print(
                                _build_error_panel(
                                    "A API respondeu com um evento de erro fora do contrato esperado. "
                                    f"Detalhe: {exc}",
                                    title="Payload Invalido",
                                )
                            )
                            return None
                        break
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

    if error_response is not None:
        console.print(
            _build_error_panel(
                error_response.detail,
                title="Falha da API",
            )
        )
        if debug and error_response.debug is not None:
            console.print(
                _build_debug_panel(
                    _format_debug_info(error_response.debug),
                    title="Debug Execucao",
                )
            )
        return None

    if final_response is None:
        console.print(
            _build_error_panel(
                "O stream SSE terminou sem emitir um evento final valido.",
                title="Stream Incompleto",
            )
        )
        return None

    if debug and final_response.metadata and final_response.metadata.debug:
        debug_text = _format_debug_info(final_response.metadata.debug)
        with Live(console=console, refresh_per_second=12) as debug_live:
            _animate_text(
                debug_live,
                debug_text,
                panel_builder=lambda t: _build_debug_panel(t, title="Debug Execucao"),
            )

    return final_response
