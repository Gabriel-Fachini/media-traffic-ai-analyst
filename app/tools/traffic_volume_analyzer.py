from __future__ import annotations

from google.cloud import bigquery

from app.clients.bigquery_client import BigQueryClient
from app.schemas.tools import TrafficVolumeInput, TrafficVolumeOutput, TrafficVolumeRow

TRAFFIC_VOLUME_SQL = """
SELECT
    COALESCE(traffic_source, 'Unknown') AS traffic_source,
    COUNT(DISTINCT id) AS user_count
FROM `bigquery-public-data.thelook_ecommerce.users`
WHERE DATE(created_at) BETWEEN @start_date AND @end_date
    AND (
            @traffic_source IS NULL
            OR LOWER(COALESCE(traffic_source, 'Unknown')) = LOWER(@traffic_source)
    )
GROUP BY COALESCE(traffic_source, 'Unknown')
ORDER BY user_count DESC
"""


def traffic_volume_analyzer(
    tool_input: TrafficVolumeInput,
    bq_client: BigQueryClient | None = None,
) -> TrafficVolumeOutput:
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

    query_rows = client.run_query(sql=TRAFFIC_VOLUME_SQL, parameters=parameters)

    rows = [
        TrafficVolumeRow(
            traffic_source=str(row["traffic_source"]),
            user_count=int(row["user_count"]),
        )
        for row in query_rows
    ]

    return TrafficVolumeOutput(
        traffic_source=tool_input.traffic_source,
        start_date=tool_input.start_date,
        end_date=tool_input.end_date,
        rows=rows,
    )
