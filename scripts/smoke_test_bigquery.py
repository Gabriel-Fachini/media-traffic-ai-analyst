from __future__ import annotations

from datetime import date, timedelta

from app.clients.bigquery_client import BigQueryClient, BigQueryClientError


def main() -> int:
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    try:
        client = BigQueryClient()
        result = client.smoke_test_thelook_dataset(
            start_date=start_date,
            end_date=end_date,
        )
    except BigQueryClientError as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("[OK] Conexao com BigQuery validada.")
    print(f"Periodo testado: {start_date} ate {end_date}")
    print(f"Usuarios unicos no periodo: {result['total_users']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
