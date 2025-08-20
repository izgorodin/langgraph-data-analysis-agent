"""Prometheus metrics collection for LGDA production observability.

Provides comprehensive metrics collection for:
- Performance metrics (response times, throughput, error rates)
- Business metrics (query types, success rates, user satisfaction)
- Resource metrics (memory, CPU, BigQuery usage, LLM tokens)
- Custom metrics (domain-specific KPIs)

Can be disabled via LGDA_DISABLE_OBSERVABILITY environment variable.
"""

import logging
import os
import time
from typing import Dict, Optional

# Prometheus client is optional - graceful degradation if not available
try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus_client not available, metrics collection disabled")

logger = logging.getLogger(__name__)


class LGDAMetrics:
    """Production-grade metrics collection for LGDA pipeline.

    Provides Prometheus-compatible metrics with graceful degradation when
    prometheus_client is not available or when observability is disabled.
    """

    def __init__(self, enabled: Optional[bool] = None):
        """Initialize metrics collector.

        Args:
            enabled: Override default enabled state. If None, uses environment.
        """
        if enabled is None:
            # Check for disable flag
            self.enabled = (
                not os.getenv("LGDA_DISABLE_OBSERVABILITY", "false").lower() == "true"
            )
        else:
            self.enabled = enabled

        # Only check PROMETHEUS_AVAILABLE if we want to be enabled
        if self.enabled and not PROMETHEUS_AVAILABLE:
            logger.warning("Metrics requested but prometheus_client not available")
            self.enabled = False

        if not self.enabled:
            logger.info("LGDA metrics collection disabled")
            return

        try:
            self._initialize_metrics()
            logger.info("LGDA metrics collection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize metrics: {e}")
            self.enabled = False

    def _initialize_metrics(self):
        """Initialize all Prometheus metrics."""
        # Request metrics
        self.requests_total = Counter(
            "lgda_requests_total", "Total requests processed", ["endpoint", "status"]
        )

        self.request_duration = Histogram(
            "lgda_request_duration_seconds",
            "Time spent processing requests",
            ["endpoint"],
        )

        # Pipeline stage metrics
        self.pipeline_stage_duration = Histogram(
            "lgda_pipeline_stage_duration_seconds",
            "Time spent in each pipeline stage",
            ["stage"],
        )

        self.pipeline_stage_errors = Counter(
            "lgda_pipeline_stage_errors_total",
            "Errors encountered in pipeline stages",
            ["stage", "error_type"],
        )

        # Business metrics
        self.queries_executed = Counter(
            "lgda_queries_executed_total", "BigQuery queries executed", ["success"]
        )

        self.insights_generated = Counter(
            "lgda_insights_generated_total",
            "Business insights generated",
            ["quality_score_range"],
        )

        self.query_cost_bytes = Histogram(
            "lgda_query_cost_bytes_processed", "Bytes processed by BigQuery queries"
        )

        # System metrics
        self.active_connections = Gauge(
            "lgda_active_connections",
            "Active connections to external services",
            ["service"],
        )

        self.memory_usage = Gauge(
            "lgda_memory_usage_bytes", "Memory usage of LGDA components", ["component"]
        )

        # LLM metrics
        self.llm_requests = Counter(
            "lgda_llm_requests_total",
            "LLM provider requests",
            ["provider", "model", "success"],
        )

        self.llm_tokens = Counter(
            "lgda_llm_tokens_total",
            "LLM tokens consumed",
            ["provider", "model", "type"],
        )

        self.llm_latency = Histogram(
            "lgda_llm_latency_seconds", "LLM request latency", ["provider", "model"]
        )

        # System info (simplified without Info metric)
        self.system_version = "1.0.0"  # Store as simple attribute

    def record_request(self, endpoint: str, status: str, duration: float):
        """Record a request with its outcome and duration."""
        if not self.enabled:
            return

        try:
            self.requests_total.labels(endpoint=endpoint, status=status).inc()
            self.request_duration.labels(endpoint=endpoint).observe(duration)
        except Exception as e:
            logger.error(f"Failed to record request metrics: {e}")

    def record_pipeline_stage(
        self, stage: str, duration: float, error_type: Optional[str] = None
    ):
        """Record pipeline stage execution metrics."""
        if not self.enabled:
            return

        try:
            self.pipeline_stage_duration.labels(stage=stage).observe(duration)
            if error_type:
                self.pipeline_stage_errors.labels(
                    stage=stage, error_type=error_type
                ).inc()
        except Exception as e:
            logger.error(f"Failed to record pipeline stage metrics: {e}")

    def record_query_execution(
        self, success: bool, bytes_processed: Optional[int] = None
    ):
        """Record BigQuery execution metrics."""
        if not self.enabled:
            return

        try:
            self.queries_executed.labels(success=str(success).lower()).inc()
            if bytes_processed:
                self.query_cost_bytes.observe(bytes_processed)
        except Exception as e:
            logger.error(f"Failed to record query metrics: {e}")

    def record_insight_generation(self, quality_score: Optional[float] = None):
        """Record business insight generation."""
        if not self.enabled:
            return

        try:
            # Categorize quality score for metrics
            if quality_score is None:
                score_range = "unknown"
            elif quality_score >= 0.8:
                score_range = "high"
            elif quality_score >= 0.6:
                score_range = "medium"
            else:
                score_range = "low"

            self.insights_generated.labels(quality_score_range=score_range).inc()
        except Exception as e:
            logger.error(f"Failed to record insight metrics: {e}")

    def record_llm_request(
        self,
        provider: str,
        model: str,
        success: bool,
        latency: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        """Record LLM provider request metrics."""
        if not self.enabled:
            return

        try:
            self.llm_requests.labels(
                provider=provider, model=model, success=str(success).lower()
            ).inc()

            self.llm_latency.labels(provider=provider, model=model).observe(latency)

            if input_tokens > 0:
                self.llm_tokens.labels(
                    provider=provider, model=model, type="input"
                ).inc(input_tokens)

            if output_tokens > 0:
                self.llm_tokens.labels(
                    provider=provider, model=model, type="output"
                ).inc(output_tokens)
        except Exception as e:
            logger.error(f"Failed to record LLM metrics: {e}")

    def update_active_connections(self, service: str, count: int):
        """Update active connection count for a service."""
        if not self.enabled:
            return

        try:
            self.active_connections.labels(service=service).set(count)
        except Exception as e:
            logger.error(f"Failed to update connection metrics: {e}")

    def update_memory_usage(self, component: str, bytes_used: int):
        """Update memory usage for a component."""
        if not self.enabled:
            return

        try:
            self.memory_usage.labels(component=component).set(bytes_used)
        except Exception as e:
            logger.error(f"Failed to update memory metrics: {e}")

    def set_system_info(self, info: Dict[str, str]):
        """Set system information labels."""
        if not self.enabled:
            return

        try:
            # Store system info without prometheus Info metric
            self.system_version = info.get("version", "unknown")
            logger.info(f"System info updated: {info}")
        except Exception as e:
            logger.error(f"Failed to set system info: {e}")


class MetricsContext:
    """Context manager for automatic metrics collection."""

    def __init__(self, metrics: LGDAMetrics, endpoint: str):
        self.metrics = metrics
        self.endpoint = endpoint
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            status = "error" if exc_type else "success"
            self.metrics.record_request(self.endpoint, status, duration)


# Global metrics instance for convenience
_global_metrics: Optional[LGDAMetrics] = None


def get_metrics() -> LGDAMetrics:
    """Get the global metrics instance, initializing if needed."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = LGDAMetrics()
    return _global_metrics


def disable_metrics():
    """Disable metrics collection globally."""
    global _global_metrics
    _global_metrics = LGDAMetrics(enabled=False)
