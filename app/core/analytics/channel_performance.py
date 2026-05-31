from __future__ import annotations

from decimal import Decimal

from google.cloud import bigquery

from app.core.analytics.models import (
    ChannelPerformanceInput,
    ChannelPerformanceOutput,
    ChannelPerformanceRow,
)
from app.core.analytics.queries import CHANNEL_PERFORMANCE_SQL
from app.infra.bigquery import BigQueryClient


def channel_performance_analyzer(
    tool_input: ChannelPerformanceInput,
    bq_client: BigQueryClient | None = None,
) -> ChannelPerformanceOutput:
    client = bq_client or BigQueryClient()

    parameters = [
        bigquery.ScalarQueryParameter("start_date", "DATE", tool_input.start_date),
        bigquery.ScalarQueryParameter("end_date", "DATE", tool_input.end_date),
        bigquery.ScalarQueryParameter(
            "traffic_source",
            "STRING",
            tool_input.traffic_source,
        ),
    ]

    query_rows = client.run_query(sql=CHANNEL_PERFORMANCE_SQL, parameters=parameters)

    rows = [
        ChannelPerformanceRow(
            traffic_source=str(row["traffic_source"]),
            total_orders=int(row["total_orders"]),
            total_revenue=Decimal(str(row["total_revenue"])),
        )
        for row in query_rows
    ]

    return ChannelPerformanceOutput(
        traffic_source=tool_input.traffic_source,
        start_date=tool_input.start_date,
        end_date=tool_input.end_date,
        rows=rows,
    )
