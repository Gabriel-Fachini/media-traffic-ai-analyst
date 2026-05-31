from __future__ import annotations

from google.cloud import bigquery

from app.core.analytics.models import TrafficVolumeInput, TrafficVolumeOutput, TrafficVolumeRow
from app.core.analytics.queries import TRAFFIC_VOLUME_SQL
from app.infra.bigquery import BigQueryClient


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
