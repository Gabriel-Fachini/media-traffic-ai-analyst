from __future__ import annotations

from datetime import date
from typing import Any

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from app.utils.config import Settings, SettingsError, get_settings


class BigQueryClientError(RuntimeError):
    pass


class BigQueryClient:
    def __init__(self, settings: Settings | None = None) -> None:
        try:
            self._settings = settings or get_settings()
        except SettingsError as exc:
            raise BigQueryClientError(str(exc)) from exc

        try:
            self._client = bigquery.Client(project=self._settings.gcp_project_id)
        except DefaultCredentialsError as exc:
            raise BigQueryClientError(
                "Credenciais do GCP nao configuradas. Defina GOOGLE_APPLICATION_CREDENTIALS no .env."
            ) from exc

    def run_query(
        self,
        sql: str,
        parameters: list[bigquery.ScalarQueryParameter] | None = None,
    ) -> list[dict[str, Any]]:
        job_config = bigquery.QueryJobConfig(
            query_parameters=parameters or [],
            use_legacy_sql=False,
        )

        try:
            query_job = self._client.query(sql, job_config=job_config)
            rows = query_job.result()
        except GoogleAPIError as exc:
            raise BigQueryClientError(
                "Falha de comunicacao com o BigQuery. Tente novamente em instantes."
            ) from exc

        return [dict(row.items()) for row in rows]

    def smoke_test_thelook_dataset(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        sql = """
        SELECT COUNT(DISTINCT id) AS total_users
        FROM `bigquery-public-data.thelook_ecommerce.users`
        WHERE DATE(created_at) BETWEEN @start_date AND @end_date
        """

        parameters = [
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]

        result = self.run_query(sql=sql, parameters=parameters)
        return result[0] if result else {"total_users": 0}
