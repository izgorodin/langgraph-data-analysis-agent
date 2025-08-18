from __future__ import annotations

from typing import Dict, List, Optional

from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

from .config import settings

_bq_client: Optional[bigquery.Client] = None


def bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(
            project=settings.bq_project, location=settings.bq_location
        )
    return _bq_client


SCHEMA_QUERY = (
    """
SELECT table_name, column_name, data_type
FROM `{}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN UNNEST(@tables)
ORDER BY table_name, ordinal_position
"""
).format(settings.dataset_id)


def get_schema(tables: List[str]) -> List[Dict]:
    client = bq_client()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("tables", "STRING", tables)],
        maximum_bytes_billed=settings.max_bytes_billed,
    )
    rows = client.query(SCHEMA_QUERY, job_config=job_config).result()
    return [dict(r) for r in rows]


def run_query(sql: str, dry_run: bool = False):
    client = bq_client()
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=settings.max_bytes_billed,
        dry_run=dry_run,
        use_query_cache=True,
    )
    try:
        job = client.query(sql, job_config=job_config)
        return job.result().to_dataframe(create_bqstorage_client=True)
    except BadRequest as e:
        raise ValueError(f"BigQuery error: {e}")
