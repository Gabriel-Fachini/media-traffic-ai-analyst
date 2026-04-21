from __future__ import annotations

import subprocess

import pytest

from app import verify


pytestmark = pytest.mark.unit


def test_tail_failure_output_returns_last_non_empty_lines() -> None:
    completed = subprocess.CompletedProcess(
        args=("poetry", "run", "ruff"),
        returncode=1,
        stdout="linha 1\n\nlinha 2\n",
        stderr="erro 1\nerro 2\n",
    )

    assert verify._tail_failure_output(completed, max_lines=3) == [
        "[stdout] linha 2",
        "[stderr] erro 1",
        "[stderr] erro 2",
    ]


def test_main_agent_mode_prints_compact_success_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(verify.subprocess, "run", fake_run)

    exit_code = verify.main(["--agent"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [step.command for step in verify.STEPS]
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "[OK] ruff",
        "[OK] compileall",
        "[OK] pyright",
        "[OK] Todas as verificacoes terminaram com sucesso.",
    ]


def test_main_agent_mode_prints_only_failure_tail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = iter(
        [
            subprocess.CompletedProcess(
                verify.STEPS[0].command,
                1,
                stdout="detalhe antigo\nlinha importante\n",
                stderr="erro importante\n",
            )
        ]
    )

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        return next(results)

    monkeypatch.setattr(verify.subprocess, "run", fake_run)

    exit_code = verify.main(["--agent"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "[FAIL] ruff terminou com codigo 1.",
        "[stdout] detalhe antigo",
        "[stdout] linha importante",
        "[stderr] erro importante",
    ]
