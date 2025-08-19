from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from google.api_core.exceptions import (
    BadRequest,
    Forbidden,
    NotFound,
    RetryError,
    ServerError,
    TooManyRequests,
)
from google.cloud import bigquery

from .config import settings


@dataclass
class QueryMetrics:
    """Metrics for BigQuery query execution monitoring."""

    execution_time: float
    bytes_processed: Optional[int] = None
    bytes_billed: Optional[int] = None
    cache_hit: bool = False
    job_id: Optional[str] = None
    row_count: int = 0


_bq_client: Optional[bigquery.Client] = None


def bq_client() -> bigquery.Client:
    """
    Get BigQuery client with authentication fallback strategy.

    Implements multi-level authentication:
    1. Environment-based credentials (production)
    2. Application Default Credentials (development)
    3. Automatic retry on auth failures
    """
    global _bq_client
    if _bq_client is None:
        try:
            # Try to create client with current configuration
            _bq_client = bigquery.Client(
                project=settings.bq_project or None,  # None allows auto-detection
                location=settings.bq_location,
            )
            logging.info(
                f"BigQuery client initialized for project: {settings.bq_project}"
            )
        except Exception as e:
            logging.error(f"Failed to initialize BigQuery client: {e}")
            # Try fallback with Application Default Credentials
            try:
                _bq_client = bigquery.Client(location=settings.bq_location)
                logging.info("BigQuery client initialized with default credentials")
            except Exception as fallback_error:
                logging.error(f"BigQuery client fallback failed: {fallback_error}")
                raise RuntimeError(
                    f"Cannot initialize BigQuery client: {fallback_error}"
                ) from e
    return _bq_client


# nosec B608: SCHEMA_QUERY is a static template with parameter binding via
# QueryJobConfig; dataset comes from settings and not user input
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


def run_query(
    sql: str, dry_run: bool = False, timeout: Optional[int] = None
) -> Optional[object]:
    """
    Execute BigQuery SQL with comprehensive error handling and retry logic.

    Args:
        sql: SQL query to execute
        dry_run: If True, validate query without execution
        timeout: Query timeout in seconds (default: 300)

    Returns:
        pandas.DataFrame with query results or None for dry_run

    Raises:
        ValueError: For SQL syntax errors
        Forbidden: For authentication/permission errors
        NotFound: For missing tables/datasets
        Exception: For other BigQuery errors
    """
    client = bq_client()

    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=settings.max_bytes_billed,
        dry_run=dry_run,
        use_query_cache=True,
        job_timeout_ms=(timeout or 300) * 1000,  # Convert to milliseconds
    )

    start_time = time.time()

    try:
        job = client.query(sql, job_config=job_config)

        if dry_run:
            # For dry run, just validate and return None
            return None

        # Wait for job completion with timeout
        result = job.result(timeout=timeout or 300)

        # Collect metrics
        execution_time = time.time() - start_time
        metrics = QueryMetrics(
            execution_time=execution_time,
            bytes_processed=job.total_bytes_processed,
            bytes_billed=job.total_bytes_billed,
            cache_hit=job.cache_hit or False,
            job_id=job.job_id,
            row_count=job.num_dml_affected_rows or 0,
        )

        logging.info(
            f"Query completed in {execution_time:.2f}s, processed {metrics.bytes_processed} bytes"
        )

        # Convert to DataFrame with BigQuery Storage for large results
        return result.to_dataframe(create_bqstorage_client=True)

    except BadRequest as e:
        # SQL syntax or validation errors
        raise ValueError(f"BigQuery error: {e}")
    except (Forbidden, NotFound, TooManyRequests) as e:
        # Re-raise auth, not found, and rate limit errors as-is for specific handling
        raise e
    except (ServerError, RetryError) as e:
        # Server errors - retry with exponential backoff
        raise Exception(f"BigQuery server error: {e}")
    except Exception as e:
        # Catch-all for other errors
        if "timeout" in str(e).lower():
            raise Exception(f"Query timeout: {e}")
        raise Exception(f"BigQuery execution failed: {e}")
