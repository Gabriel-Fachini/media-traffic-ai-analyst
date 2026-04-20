from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest

from app.tools.channel_performance_analyzer import (
    CHANNEL_PERFORMANCE_SQL,
    channel_performance_analyzer,
)
from app.tools.traffic_volume_analyzer import (
    TRAFFIC_VOLUME_SQL,
    traffic_volume_analyzer,
)
from app.schemas.tools import ChannelPerformanceInput, TrafficVolumeInput


pytestmark = pytest.mark.unit


class FakeBigQueryClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[Any] | None]] = []

    def run_query(
        self,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((sql, parameters))
        return self.rows


def _parameter_map(parameters: list[Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for parameter in parameters:
        payload = parameter.to_api_repr()
        mapped[payload["name"]] = {
            "type": payload["parameterType"]["type"],
            "value": payload["parameterValue"]["value"],
        }
    return mapped


def test_traffic_volume_analyzer_builds_query_parameters_and_maps_rows() -> None:
    fake_client = FakeBigQueryClient(
        rows=[
            {"traffic_source": "Search", "user_count": 10},
            {"traffic_source": "Organic", "user_count": 5},
        ]
    )

    result = traffic_volume_analyzer(
        TrafficVolumeInput(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        bq_client=cast(Any, fake_client),
    )

    assert len(fake_client.calls) == 1
    sql, parameters = fake_client.calls[0]
    assert sql == TRAFFIC_VOLUME_SQL
    assert parameters is not None
    mapped_parameters = _parameter_map(parameters)
    assert "@start_date" in sql
    assert "@end_date" in sql
    assert "@traffic_source" in sql
    assert mapped_parameters == {
        "start_date": {"type": "DATE", "value": "2024-01-01"},
        "end_date": {"type": "DATE", "value": "2024-01-31"},
        "traffic_source": {"type": "STRING", "value": None},
    }
    assert result.traffic_source is None
    assert result.rows[0].traffic_source == "Search"
    assert result.rows[0].user_count == 10
    assert result.rows[1].traffic_source == "Organic"
    assert result.rows[1].user_count == 5


def test_channel_performance_analyzer_builds_query_parameters_and_maps_rows() -> None:
    fake_client = FakeBigQueryClient(
        rows=[
            {
                "traffic_source": "Search",
                "total_orders": 7,
                "total_revenue": "1234.56",
            }
        ]
    )

    result = channel_performance_analyzer(
        ChannelPerformanceInput(
            traffic_source="Search",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        bq_client=cast(Any, fake_client),
    )

    assert len(fake_client.calls) == 1
    sql, parameters = fake_client.calls[0]
    assert sql == CHANNEL_PERFORMANCE_SQL
    assert parameters is not None
    mapped_parameters = _parameter_map(parameters)
    assert "COUNT(DISTINCT o.order_id)" in CHANNEL_PERFORMANCE_SQL
    assert "ROUND(SUM(CAST(oi.sale_price AS NUMERIC)), 2)" in CHANNEL_PERFORMANCE_SQL
    assert mapped_parameters == {
        "start_date": {"type": "DATE", "value": "2024-01-01"},
        "end_date": {"type": "DATE", "value": "2024-01-31"},
        "traffic_source": {"type": "STRING", "value": "Search"},
    }
    assert result.traffic_source == "Search"
    assert result.rows[0].traffic_source == "Search"
    assert result.rows[0].total_orders == 7
    assert result.rows[0].total_revenue == Decimal("1234.56")
