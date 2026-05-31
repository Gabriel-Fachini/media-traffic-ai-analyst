#!/usr/bin/env python3
"""PreToolUse guard: block non-parametrized SQL in BigQuery code.

Core project invariant: SQL is ALWAYS parametrized via
bigquery.ScalarQueryParameter. User input is never concatenated/interpolated
into a query string. This hook enforces it mechanically on the files that
build queries.

Heuristic: flag f-string / .format() / % / + concatenation that appears near a
SQL keyword in the newly written content. Conservative — only inspects the code
being added (new_string / content), not the whole file.

Exit codes:
  0 -> allow
  2 -> block (stderr fed back to Claude)
"""
from __future__ import annotations

import json
import re
import sys

# Files responsible for building / running BigQuery SQL.
GUARDED = (
    "app/core/analytics/queries.py",
    "app/infra/bigquery.py",
    "app/tools/",
    "bigquery_client.py",
)

SQL_KEYWORD = re.compile(r"\b(SELECT|FROM|WHERE|JOIN|GROUP\s+BY|ORDER\s+BY)\b", re.I)

# Interpolation signatures that are dangerous inside a SQL literal.
DANGER = (
    re.compile(r'f"""[^"]*\{', re.S),     # f-triple-quote with a brace
    re.compile(r"f'''[^']*\{", re.S),
    re.compile(r'f"[^"]*\{'),             # f-string with a brace
    re.compile(r"f'[^']*\{"),
    re.compile(r"\.format\s*\("),         # .format(
    re.compile(r'"\s*%\s*\('),            # "..." % (
    re.compile(r'"\s*\+\s*\w'),           # "..." + var
)


def _is_guarded(path: str) -> bool:
    return any(g in path for g in GUARDED)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool not in ("Edit", "Write"):
        return 0

    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ""
    if not _is_guarded(path):
        return 0

    content = ti.get("new_string") or ti.get("content") or ""
    if not SQL_KEYWORD.search(content):
        return 0  # no SQL here, nothing to enforce

    dataset_only_interpolation = re.sub(r"\{DATASET_ID\}", "", content)

    for pat in DANGER:
        m = pat.search(dataset_only_interpolation)
        if m:
            print(
                "BLOCKED: looks like non-parametrized SQL in "
                f"'{path}' (matched: {m.group(0)!r}). "
                "Project invariant: never interpolate/concat into a query. "
                "Use bigquery.ScalarQueryParameter and @named placeholders.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
