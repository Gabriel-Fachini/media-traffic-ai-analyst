#!/usr/bin/env python3
"""PostToolUse: lint just-edited Python files with ruff.

Closes the verify loop without relying on the agent to remember `poetry run
verify`. Runs only ruff (fast); pyright/compileall stay in the manual gate.

Exit codes:
  0 -> clean (silent)
  2 -> lint errors (stderr fed back to Claude as feedback, not a hard block)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

WATCHED_PREFIXES = ("app/", "scripts/", "tests/")


def _rel(path: str) -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name", "") not in ("Edit", "Write"):
        return 0

    path = (data.get("tool_input", {}) or {}).get("file_path", "") or ""
    if not path.endswith(".py"):
        return 0

    rel = _rel(path)
    if not rel.startswith(WATCHED_PREFIXES):
        return 0

    try:
        proc = subprocess.run(
            ("poetry", "run", "ruff", "check", rel),
            cwd=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return 0  # tooling missing/slow: do not nag

    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        print(f"ruff found issues in {rel}:\n{out.strip()}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
