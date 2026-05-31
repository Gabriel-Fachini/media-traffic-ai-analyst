from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class VerificationStep:
    label: str
    command: tuple[str, ...]


STEPS = (
    VerificationStep(
        label="ruff",
        command=("poetry", "run", "ruff", "check", "app", "scripts", "tests"),
    ),
    VerificationStep(
        label="compileall",
        command=("python3", "-m", "compileall", "app", "scripts", "tests"),
    ),
    VerificationStep(
        label="pyright",
        command=("poetry", "run", "pyright"),
    ),
)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify",
        description="Executa o gate local de verificacao do projeto.",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Reduz o output ao minimo necessario para uso iterativo por agentes.",
    )
    return parser


def _tail_failure_output(
    completed: subprocess.CompletedProcess[str],
    *,
    max_lines: int = 20,
) -> list[str]:
    output_lines: list[str] = []
    for stream_name, stream_content in (
        ("stdout", completed.stdout or ""),
        ("stderr", completed.stderr or ""),
    ):
        for line in stream_content.splitlines():
            stripped_line = line.strip()
            if stripped_line:
                output_lines.append(f"[{stream_name}] {stripped_line}")

    return output_lines[-max_lines:]


def _run_step(step: VerificationStep, *, agent: bool) -> int:
    if agent:
        completed = subprocess.run(
            step.command,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            print(
                f"[FAIL] {step.label} terminou com codigo {completed.returncode}.",
                file=sys.stderr,
            )
            failure_output = _tail_failure_output(completed)
            if failure_output:
                print("\n".join(failure_output), file=sys.stderr)
            return completed.returncode

        print(f"[OK] {step.label}")
        return 0

    print(f"[RUN] {step.label}: {_format_command(step.command)}")
    completed = subprocess.run(step.command, check=False)

    if completed.returncode != 0:
        print(
            f"[FAIL] {step.label} terminou com codigo {completed.returncode}.",
            file=sys.stderr,
        )
        return completed.returncode

    print(f"[OK] {step.label}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    for step in STEPS:
        exit_code = _run_step(step, agent=args.agent)
        if exit_code != 0:
            return exit_code

    print("[OK] Todas as verificacoes terminaram com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
