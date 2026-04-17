from __future__ import annotations

from decimal import Decimal

from google.cloud import bigquery

from app.clients.bigquery_client import BigQueryClient
from app.schemas.tools import (
    ChannelPerformanceInput,
    ChannelPerformanceOutput,
    ChannelPerformanceRow,
)

CHANNEL_PERFORMANCE_SQL = """
SELECT
    COALESCE(u.traffic_source, 'Unknown') AS traffic_source,
    -- Each order can have multiple order_items rows, so DISTINCT avoids overcounting.
    COUNT(DISTINCT o.order_id) AS total_orders,
    COALESCE(ROUND(SUM(CAST(oi.sale_price AS NUMERIC)), 2), 0) AS total_revenue
FROM `bigquery-public-data.thelook_ecommerce.users` u
INNER JOIN `bigquery-public-data.thelook_ecommerce.orders` o
    ON u.id = o.user_id
INNER JOIN `bigquery-public-data.thelook_ecommerce.order_items` oi
    ON o.order_id = oi.order_id
WHERE DATE(o.created_at) BETWEEN @start_date AND @end_date
    AND (
            @traffic_source IS NULL
            OR LOWER(COALESCE(u.traffic_source, 'Unknown')) = LOWER(@traffic_source)
    )
GROUP BY COALESCE(u.traffic_source, 'Unknown')
ORDER BY total_revenue DESC, total_orders DESC
"""


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
