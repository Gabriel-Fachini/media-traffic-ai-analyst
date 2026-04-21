from __future__ import annotations

from types import MethodType
from typing import Any

import pytest


def _summary_stats_without_warnings(self: Any) -> None:
    warnings = self.stats.pop("warnings", None)
    try:
        self._original_summary_stats()
    finally:
        if warnings is not None:
            self.stats["warnings"] = warnings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--agent",
        action="store_true",
        default=False,
        help="Minimiza o output do pytest para iteracoes orientadas por agente.",
    )


def pytest_configure(config: pytest.Config) -> None:
    if not config.getoption("--agent"):
        return

    config.option.verbose = -1
    config.option.disable_warnings = True
    terminal_reporter = config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.report_collect = MethodType(
            lambda self, final=False: None,
            terminal_reporter,
        )
        terminal_reporter._original_summary_stats = terminal_reporter.summary_stats
        terminal_reporter.summary_stats = MethodType(
            _summary_stats_without_warnings,
            terminal_reporter,
        )

    config.option.reportchars = ""
    config.option.tbstyle = "line"


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    config = session.config
    if not config.getoption("--agent"):
        return

    config.option.verbose = -1
    config.option.disable_warnings = True


def pytest_report_teststatus(
    report: pytest.TestReport,
    config: pytest.Config,
) -> tuple[str, str, str] | None:
    if not config.getoption("--agent"):
        return None

    if report.failed:
        if report.when == "call":
            return ("failed", "F", "FAILED")
        return ("error", "E", "ERROR")

    if report.skipped:
        return ("skipped", "", "")

    if report.when == "call":
        return ("passed", "", "")

    return ("", "", "")
