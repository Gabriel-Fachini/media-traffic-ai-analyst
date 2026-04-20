from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Inclui os testes marcados como live junto com a suite padrao.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-live"):
        return

    markexpr = (config.option.markexpr or "").strip()
    if "live" in markexpr:
        return

    skip_live = pytest.mark.skip(
        reason=(
            "Testes live sao opt-in. Use `poetry run pytest -m live` "
            "ou `poetry run pytest --run-live`."
        )
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
