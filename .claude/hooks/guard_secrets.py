#!/usr/bin/env python3
"""PreToolUse guard: block access to secret files.

Protects API keys (OpenAI/Anthropic) and the GCP service account from being
read into the model context or edited. .gitignore protects git; this protects
the transcript/context.

Exit codes:
  0 -> allow
  2 -> block (stderr is fed back to Claude as the reason)
"""
from __future__ import annotations

import json
import re
import sys

# Path fragments that identify a secret. Matched case-insensitively as substrings.
SECRET_PATTERNS = (
    r"(^|/)\.env($|\.|/)",          # .env, .env.local (NOT .env.example)
    r"credentials/.*\.json",        # GCP service account
    r"google\.json",
)

# Bash subcommands that would dump file contents.
BASH_READERS = ("cat", "less", "more", "head", "tail", "bat", "xxd", "od", "strings")


def _is_secret_path(path: str) -> bool:
    if not path:
        return False
    low = path.lower()
    if low.endswith(".env.example"):
        return False
    return any(re.search(p, low) for p in SECRET_PATTERNS)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # never block on our own parse failure

    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}

    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if _is_secret_path(path):
            print(
                f"BLOCKED: '{path}' holds secrets (API keys / GCP service account). "
                "Do not read or edit it. Use .env.example as the reference instead.",
                file=sys.stderr,
            )
            return 2

    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        mentions_reader = any(re.search(rf"\b{r}\b", cmd) for r in BASH_READERS)
        if mentions_reader and any(
            re.search(p, cmd.lower()) for p in SECRET_PATTERNS
        ) and ".env.example" not in cmd:
            print(
                "BLOCKED: command would dump a secret file (.env / credentials). "
                "Refer to .env.example instead.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
