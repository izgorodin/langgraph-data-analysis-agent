"""Test suite for LGDA observability metrics collection."""

import os
import time
from unittest.mock import Mock, patch

import pytest

from src.observability.metrics import (
    LGDAMetrics,
    MetricsContext,
    disable_metrics,
    get_metrics,
)


class TestLGDAMetrics:
    """Test cases for metrics collection functionality."""

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_initialization_enabled(self):
        """Test metrics initialization when enabled."""
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "false"}):
            with patch("src.observability.metrics.LGDAMetrics._initialize_metrics"):
                metrics = LGDAMetrics()
                assert metrics.enabled is True

    def test_metrics_initialization_disabled(self):
        """Test metrics initialization when disabled."""
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            metrics = LGDAMetrics()
            assert metrics.enabled is False

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_explicit_enable_disable(self):
        """Test explicit enable/disable override."""
        with patch("src.observability.metrics.LGDAMetrics._initialize_metrics"):
            metrics_enabled = LGDAMetrics(enabled=True)
            assert metrics_enabled.enabled is True

        metrics_disabled = LGDAMetrics(enabled=False)
        assert metrics_disabled.enabled is False

    def test_metrics_graceful_degradation_without_prometheus(self):
        """Test graceful degradation when prometheus_client is not available."""
        with patch("src.observability.metrics.PROMETHEUS_AVAILABLE", False):
            metrics = LGDAMetrics()
            assert metrics.enabled is False

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_record_request_metrics(self):
        """Test request metrics recording."""
        metrics = LGDAMetrics(enabled=True)

        # Should not raise exception even without actual Prometheus
        metrics.record_request("test_endpoint", "success", 1.5)
        metrics.record_request("test_endpoint", "error", 0.5)

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_record_pipeline_stage_metrics(self):
        """Test pipeline stage metrics recording."""
        metrics = LGDAMetrics(enabled=True)

        metrics.record_pipeline_stage("plan", 2.0)
        metrics.record_pipeline_stage("execute_sql", 5.0, "timeout_error")

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_record_query_execution_metrics(self):
        """Test BigQuery execution metrics."""
        metrics = LGDAMetrics(enabled=True)

        metrics.record_query_execution(success=True, bytes_processed=1000000)
        metrics.record_query_execution(success=False)

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_record_insight_generation_metrics(self):
        """Test insight generation metrics."""
        metrics = LGDAMetrics(enabled=True)

        metrics.record_insight_generation(quality_score=0.9)
        metrics.record_insight_generation(quality_score=0.5)
        metrics.record_insight_generation()  # No score provided

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_record_llm_request_metrics(self):
        """Test LLM request metrics."""
        metrics = LGDAMetrics(enabled=True)

        metrics.record_llm_request(
            provider="gemini",
            model="gemini-1.5-pro",
            success=True,
            latency=2.5,
            input_tokens=100,
            output_tokens=50,
        )

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_update_system_metrics(self):
        """Test system metrics updates."""
        metrics = LGDAMetrics(enabled=True)

        metrics.update_active_connections("bigquery", 5)
        metrics.update_memory_usage("agent", 1024000)

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_set_system_info(self):
        """Test system info setting."""
        metrics = LGDAMetrics(enabled=True)

        info = {"version": "1.0.0", "environment": "test", "python_version": "3.12"}
        metrics.set_system_info(info)

    def test_metrics_disabled_operations(self):
        """Test that operations work when metrics are disabled."""
        metrics = LGDAMetrics(enabled=False)

        # All operations should work without raising exceptions
        metrics.record_request("test", "success", 1.0)
        metrics.record_pipeline_stage("test", 1.0)
        metrics.record_query_execution(True)
        metrics.record_insight_generation(0.8)
        metrics.record_llm_request("test", "test", True, 1.0)
        metrics.update_active_connections("test", 1)
        metrics.update_memory_usage("test", 1000)
        metrics.set_system_info({"test": "value"})


class TestMetricsContext:
    """Test cases for metrics context manager."""

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_context_success(self):
        """Test metrics context for successful operations."""
        metrics = LGDAMetrics(enabled=True)

        with MetricsContext(metrics, "test_operation") as ctx:
            time.sleep(0.01)  # Simulate work

        # Context should complete without error
        assert ctx.metrics == metrics
        assert ctx.endpoint == "test_operation"

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_context_error(self):
        """Test metrics context for failed operations."""
        metrics = LGDAMetrics(enabled=True)

        with pytest.raises(ValueError):
            with MetricsContext(metrics, "test_operation"):
                raise ValueError("Test error")


class TestGlobalMetrics:
    """Test cases for global metrics functionality."""

    def test_get_metrics_singleton(self):
        """Test that get_metrics returns singleton instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2

    def test_disable_metrics_global(self):
        """Test global metrics disable."""
        disable_metrics()
        metrics = get_metrics()
        assert metrics.enabled is False

    def teardown_method(self):
        """Reset global metrics after each test."""
        import src.observability.metrics

        src.observability.metrics._global_metrics = None


class TestMetricsIntegration:
    """Integration tests for metrics with other components."""

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_with_real_timing(self):
        """Test metrics collection with actual timing."""
        metrics = LGDAMetrics(enabled=True)

        start_time = time.time()
        time.sleep(0.01)  # Simulate work
        duration = time.time() - start_time

        metrics.record_request("integration_test", "success", duration)
        assert duration > 0

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_error_handling(self):
        """Test that metrics errors don't break functionality."""
        metrics = LGDAMetrics(enabled=True)

        # Mock a method to raise an error
        with patch.object(
            metrics, "_initialize_metrics", side_effect=Exception("Test error")
        ):
            metrics = LGDAMetrics(enabled=True)
            assert metrics.enabled is False

    def test_metrics_environment_configuration(self):
        """Test metrics configuration via environment variables."""
        # Test with observability disabled
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            metrics = LGDAMetrics()
            assert metrics.enabled is False

        # Test with observability enabled
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "false"}):
            metrics = LGDAMetrics()
            # Will be enabled if prometheus is available

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_metrics_performance_impact(self):
        """Test that metrics collection has minimal performance impact."""
        metrics = LGDAMetrics(enabled=True)

        # Test many rapid operations
        start_time = time.time()
        for i in range(100):
            metrics.record_request(f"test_{i}", "success", 0.001)
        duration = time.time() - start_time

        # Should complete quickly (less than 1 second for 100 operations)
        assert duration < 1.0
