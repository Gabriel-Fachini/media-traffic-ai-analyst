from __future__ import annotations

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


def main() -> int:
    for step in STEPS:
        print(f"[RUN] {step.label}: {_format_command(step.command)}")
        completed = subprocess.run(step.command, check=False)
        if completed.returncode != 0:
            print(
                f"[FAIL] {step.label} terminou com codigo {completed.returncode}.",
                file=sys.stderr,
            )
            return completed.returncode
        print(f"[OK] {step.label}")

    print("[OK] Todas as verificacoes terminaram com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
