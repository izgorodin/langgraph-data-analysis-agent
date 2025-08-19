"""Enhanced metrics collection for BigQuery operations."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class QueryMetrics:
    """Enhanced metrics for BigQuery query execution monitoring."""

    execution_time: float
    bytes_processed: Optional[int] = None
    bytes_billed: Optional[int] = None
    cache_hit: bool = False
    job_id: Optional[str] = None
    row_count: int = 0
    retries: int = 0
    breaker_state: str = "closed"

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging."""
        return asdict(self)

    def log_structured(self, level: int = logging.INFO) -> None:
        """Log metrics in structured format."""
        log_data = {
            "job_id": self.job_id,
            "elapsed_ms": int(self.execution_time * 1000),
            "bytes_processed": self.bytes_processed,
            "bytes_billed": self.bytes_billed,
            "cache_hit": self.cache_hit,
            "row_count": self.row_count,
            "retries": self.retries,
            "breaker_state": self.breaker_state,
        }

        # Remove None values and convert Mock objects to strings for cleaner logs
        clean_log_data = {}
        for k, v in log_data.items():
            if v is not None:
                # Handle Mock objects and other non-serializable types
                try:
                    json.dumps(v)  # Test if it's JSON serializable
                    clean_log_data[k] = v
                except (TypeError, ValueError):
                    # Convert non-serializable objects to string representation
                    clean_log_data[k] = str(v)

        logging.log(level, "BigQuery query metrics: %s", json.dumps(clean_log_data))


class MetricsCollector:
    """Utility class for collecting and managing query metrics."""

    def __init__(self) -> None:
        self.start_time: Optional[float] = None
        self.metrics: Optional[QueryMetrics] = None

    def start_timer(self) -> None:
        """Start timing a query execution."""
        self.start_time = time.time()

    def create_metrics(
        self,
        job_id: Optional[str] = None,
        bytes_processed: Optional[int] = None,
        bytes_billed: Optional[int] = None,
        cache_hit: bool = False,
        row_count: int = 0,
        retries: int = 0,
        breaker_state: str = "closed",
    ) -> QueryMetrics:
        """Create metrics object with current timing."""
        if self.start_time is None:
            execution_time = 0.0
        else:
            execution_time = time.time() - self.start_time

        self.metrics = QueryMetrics(
            execution_time=execution_time,
            bytes_processed=bytes_processed,
            bytes_billed=bytes_billed,
            cache_hit=cache_hit,
            job_id=job_id,
            row_count=row_count,
            retries=retries,
            breaker_state=breaker_state,
        )
        return self.metrics

    def get_metrics(self) -> Optional[QueryMetrics]:
        """Get the current metrics object."""
        return self.metrics
