"""Test suite for LGDA observability business metrics functionality."""

import pytest
import time
from unittest.mock import patch, Mock

from src.observability.business_metrics import (
    BusinessMetrics,
    BusinessMetric,
    QueryComplexity,
    InsightQuality,
    get_business_metrics,
    disable_business_metrics
)


class TestBusinessMetric:
    """Test cases for BusinessMetric data class."""
    
    def test_business_metric_creation(self):
        """Test business metric creation with defaults."""
        metric = BusinessMetric("test_metric", 1.0)
        
        assert metric.metric_name == "test_metric"
        assert metric.value == 1.0
        assert metric.timestamp > 0
        assert isinstance(metric.dimensions, dict)
        assert isinstance(metric.metadata, dict)
    
    def test_business_metric_with_data(self):
        """Test business metric creation with full data."""
        dimensions = {"category": "test", "success": "true"}
        metadata = {"details": "test data"}
        
        metric = BusinessMetric(
            "test_metric",
            2.5,
            dimensions=dimensions,
            metadata=metadata
        )
        
        assert metric.dimensions == dimensions
        assert metric.metadata == metadata
    
    def test_business_metric_to_dict(self):
        """Test business metric serialization."""
        metric = BusinessMetric(
            "test_metric",
            1.0,
            dimensions={"key": "value"},
            metadata={"meta": "data"}
        )
        
        result = metric.to_dict()
        
        assert result["metric_name"] == "test_metric"
        assert result["value"] == 1.0
        assert "timestamp" in result
        assert result["dimensions"] == {"key": "value"}
        assert result["metadata"] == {"meta": "data"}


class TestBusinessMetrics:
    """Test cases for business metrics tracking functionality."""
    
    def test_business_metrics_initialization_enabled(self):
        """Test business metrics initialization when enabled."""
        with patch.dict("os.environ", {"LGDA_DISABLE_OBSERVABILITY": "false"}):
            metrics = BusinessMetrics()
            assert metrics.enabled is True
    
    def test_business_metrics_initialization_disabled(self):
        """Test business metrics initialization when disabled."""
        with patch.dict("os.environ", {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            metrics = BusinessMetrics()
            assert metrics.enabled is False
    
    def test_business_metrics_explicit_enable_disable(self):
        """Test explicit enable/disable override."""
        metrics_enabled = BusinessMetrics(enabled=True)
        metrics_disabled = BusinessMetrics(enabled=False)
        
        assert metrics_enabled.enabled is True
        assert metrics_disabled.enabled is False
    
    def test_track_query_success_rate(self):
        """Test query success rate tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        # Track successful query
        metrics.track_query_success_rate(
            success=True,
            question="Test question",
            complexity=QueryComplexity.MEDIUM,
            execution_time=2.5
        )
        
        # Track failed query
        metrics.track_query_success_rate(
            success=False,
            question="Failed question",
            complexity=QueryComplexity.COMPLEX,
            error_type="TimeoutError"
        )
        
        assert len(metrics.metrics_buffer) == 2
        
        success_metric = metrics.metrics_buffer[0]
        assert success_metric.metric_name == "query_success_rate"
        assert success_metric.value == 1.0
        assert success_metric.dimensions["success"] == "true"
        assert success_metric.dimensions["complexity"] == "medium"
        
        failure_metric = metrics.metrics_buffer[1]
        assert failure_metric.value == 0.0
        assert failure_metric.dimensions["success"] == "false"
        assert failure_metric.dimensions["error_type"] == "TimeoutError"
    
    def test_track_insight_quality(self):
        """Test insight quality tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        # Track high quality insight
        metrics.track_insight_quality(
            feedback_score=0.9,
            question="Great question",
            insight_length=500,
            user_rating=5
        )
        
        # Track low quality insight
        metrics.track_insight_quality(
            feedback_score=0.3,
            question="Poor question",
            insight_length=100,
            user_rating=2
        )
        
        assert len(metrics.metrics_buffer) == 2
        
        high_quality = metrics.metrics_buffer[0]
        assert high_quality.metric_name == "insight_quality_score"
        assert high_quality.value == 0.9
        assert high_quality.dimensions["quality_category"] == "high"
        assert high_quality.dimensions["user_rating"] == "5"
        
        low_quality = metrics.metrics_buffer[1]
        assert low_quality.value == 0.3
        assert low_quality.dimensions["quality_category"] == "poor"  # 0.3 maps to "poor"
        assert low_quality.dimensions["user_rating"] == "2"
    
    def test_track_resource_efficiency(self):
        """Test resource efficiency tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_resource_efficiency(
            query_cost=0.05,
            insight_value=0.8,
            bytes_processed=1000000,
            execution_time=3.0
        )
        
        # Should create efficiency ratio metric and separate cost/value metrics
        assert len(metrics.metrics_buffer) == 3
        
        efficiency_metric = next(m for m in metrics.metrics_buffer if m.metric_name == "resource_efficiency")
        assert efficiency_metric.value == 0.8 / 0.05  # 16.0
        assert "cost_category" in efficiency_metric.dimensions
        assert "value_category" in efficiency_metric.dimensions
    
    def test_track_user_patterns(self):
        """Test user pattern tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_user_patterns(
            question_category="analytics",
            complexity="medium",
            user_id="user123",
            session_id="session456",
            repeat_question=False
        )
        
        assert len(metrics.metrics_buffer) == 1
        
        pattern_metric = metrics.metrics_buffer[0]
        assert pattern_metric.metric_name == "user_engagement"
        assert pattern_metric.dimensions["question_category"] == "analytics"
        assert pattern_metric.dimensions["complexity"] == "medium"
        assert pattern_metric.dimensions["repeat_question"] == "false"
        assert pattern_metric.dimensions["user_type"] == "returning"
        
        # Check session data
        assert "session456" in metrics.session_data
        session = metrics.session_data["session456"]
        assert session["question_count"] == 1
        assert "analytics" in session["categories"]
        assert "medium" in session["complexity_levels"]
    
    def test_track_pipeline_performance(self):
        """Test pipeline performance tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_pipeline_performance(
            stage="execute_sql",
            duration=5.5,
            success=True,
            memory_usage=1024000
        )
        
        assert len(metrics.metrics_buffer) == 1
        
        performance_metric = metrics.metrics_buffer[0]
        assert performance_metric.metric_name == "pipeline_performance"
        assert performance_metric.value == 5.5
        assert performance_metric.dimensions["stage"] == "execute_sql"
        assert performance_metric.dimensions["success"] == "true"
        assert "performance_category" in performance_metric.dimensions
    
    def test_track_error_patterns(self):
        """Test error pattern tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_error_patterns(
            error_type="TimeoutError",
            stage="execute_sql",
            recovery_successful=True,
            error_frequency=3
        )
        
        assert len(metrics.metrics_buffer) == 1
        
        error_metric = metrics.metrics_buffer[0]
        assert error_metric.metric_name == "error_patterns"
        assert error_metric.dimensions["error_type"] == "TimeoutError"
        assert error_metric.dimensions["stage"] == "execute_sql"
        assert error_metric.dimensions["recovery_successful"] == "true"
    
    def test_track_feature_usage(self):
        """Test feature usage tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_feature_usage(
            feature="sql_validation",
            usage_context="automated",
            success=True,
            user_satisfaction=0.85
        )
        
        assert len(metrics.metrics_buffer) == 1
        
        feature_metric = metrics.metrics_buffer[0]
        assert feature_metric.metric_name == "feature_usage"
        assert feature_metric.dimensions["feature"] == "sql_validation"
        assert feature_metric.dimensions["context"] == "automated"
        assert feature_metric.dimensions["success"] == "true"
        assert feature_metric.dimensions["satisfaction_level"] == "high"
    
    def test_track_business_kpi(self):
        """Test business KPI tracking."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_business_kpi(
            kpi_name="user_retention",
            value=0.75,
            target_value=0.80,
            dimensions={"period": "monthly", "segment": "premium"}
        )
        
        assert len(metrics.metrics_buffer) == 1
        
        kpi_metric = metrics.metrics_buffer[0]
        assert kpi_metric.metric_name == "business_kpi_user_retention"
        assert kpi_metric.value == 0.75
        assert kpi_metric.dimensions["period"] == "monthly"
        assert kpi_metric.metadata["target_value"] == 0.80
        assert kpi_metric.metadata["target_achievement"] == 0.75 / 0.80
    
    def test_get_session_summary(self):
        """Test session summary generation."""
        metrics = BusinessMetrics(enabled=True)
        
        # Track some user patterns to create session data
        metrics.track_user_patterns("analytics", "medium", session_id="test_session")
        metrics.track_user_patterns("reporting", "simple", session_id="test_session")
        
        summary = metrics.get_session_summary("test_session")
        
        assert summary is not None
        assert summary["session_id"] == "test_session"
        assert summary["question_count"] == 2
        assert summary["unique_categories"] == 2
        assert "medium" in summary["complexity_range"]  # Check the complexity range instead
        assert "medium" in summary["complexity_range"]
    
    def test_get_session_summary_nonexistent(self):
        """Test session summary for nonexistent session."""
        metrics = BusinessMetrics(enabled=True)
        
        summary = metrics.get_session_summary("nonexistent")
        assert summary is None
    
    def test_get_metrics_summary(self):
        """Test metrics summary generation."""
        metrics = BusinessMetrics(enabled=True)
        
        # Add some test metrics
        metrics.track_query_success_rate(True, "test")
        metrics.track_insight_quality(0.8, "test")
        
        summary = metrics.get_metrics_summary(hours=24)
        
        assert summary["enabled"] is True
        assert summary["hours"] == 24
        assert summary["metrics_count"] == 2
        assert "metrics_by_type" in summary
        assert "query_success_rate" in summary["metrics_by_type"]
        assert "insight_quality_score" in summary["metrics_by_type"]
    
    def test_get_metrics_summary_disabled(self):
        """Test metrics summary when disabled."""
        metrics = BusinessMetrics(enabled=False)
        
        summary = metrics.get_metrics_summary()
        assert summary["enabled"] is False
    
    def test_export_metrics(self):
        """Test metrics export functionality."""
        metrics = BusinessMetrics(enabled=True)
        
        metrics.track_query_success_rate(True, "test")
        
        exported = metrics.export_metrics(format="json")
        
        import json
        data = json.loads(exported)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["metric_name"] == "query_success_rate"
    
    def test_export_metrics_invalid_format(self):
        """Test metrics export with invalid format."""
        metrics = BusinessMetrics(enabled=True)
        
        with pytest.raises(ValueError):
            metrics.export_metrics(format="xml")
    
    def test_clear_metrics_buffer(self):
        """Test metrics buffer cleanup."""
        metrics = BusinessMetrics(enabled=True)
        
        # Add some metrics
        metrics.track_query_success_rate(True, "test")
        metrics.track_insight_quality(0.8, "test")
        
        assert len(metrics.metrics_buffer) == 2
        
        # Clear with very short retention (0 hours = clear all)
        metrics.clear_metrics_buffer(older_than_hours=0)
        
        assert len(metrics.metrics_buffer) == 0
    
    def test_categorization_methods(self):
        """Test internal categorization methods."""
        metrics = BusinessMetrics(enabled=True)
        
        # Test cost categorization
        assert metrics._categorize_cost(0.005) == "low"
        assert metrics._categorize_cost(0.05) == "medium"
        assert metrics._categorize_cost(0.5) == "high"
        assert metrics._categorize_cost(5.0) == "very_high"
        
        # Test value categorization
        assert metrics._categorize_value(0.2) == "low"
        assert metrics._categorize_value(0.5) == "medium"
        assert metrics._categorize_value(0.7) == "high"
        assert metrics._categorize_value(0.9) == "very_high"
        
        # Test performance categorization
        assert metrics._categorize_performance(2.0) == "fast"
        assert metrics._categorize_performance(10.0) == "medium"
        assert metrics._categorize_performance(30.0) == "slow"
        assert metrics._categorize_performance(120.0) == "very_slow"
        
        # Test satisfaction categorization
        assert metrics._categorize_satisfaction(0.9) == "high"
        assert metrics._categorize_satisfaction(0.7) == "medium"
        assert metrics._categorize_satisfaction(0.5) == "low"
        assert metrics._categorize_satisfaction(0.2) == "very_low"
    
    def test_disabled_operations(self):
        """Test that operations work when metrics are disabled."""
        metrics = BusinessMetrics(enabled=False)
        
        # All operations should work without raising exceptions
        metrics.track_query_success_rate(True, "test")
        metrics.track_insight_quality(0.8, "test")
        metrics.track_resource_efficiency(0.1, 0.8)
        metrics.track_user_patterns("test", "simple")
        metrics.track_pipeline_performance("test", 1.0, True)
        metrics.track_error_patterns("error", "stage", False)
        metrics.track_feature_usage("feature", "context", True)
        metrics.track_business_kpi("test", 1.0)
        
        assert len(metrics.metrics_buffer) == 0


class TestGlobalBusinessMetrics:
    """Test cases for global business metrics functionality."""
    
    def test_get_business_metrics_singleton(self):
        """Test that get_business_metrics returns singleton instance."""
        metrics1 = get_business_metrics()
        metrics2 = get_business_metrics()
        
        assert metrics1 is metrics2
    
    def test_disable_business_metrics_global(self):
        """Test global business metrics disable."""
        disable_business_metrics()
        metrics = get_business_metrics()
        assert metrics.enabled is False
    
    def teardown_method(self):
        """Reset global business metrics after each test."""
        import src.observability.business_metrics
        src.observability.business_metrics._global_business_metrics = None


class TestBusinessMetricsIntegration:
    """Integration tests for business metrics functionality."""
    
    def test_metrics_with_real_timing(self):
        """Test business metrics with actual timing."""
        metrics = BusinessMetrics(enabled=True)
        
        start_time = time.time()
        time.sleep(0.01)  # Simulate work
        
        # Metrics should handle real timestamps
        metrics.track_query_success_rate(True, "test")
        
        assert len(metrics.metrics_buffer) == 1
        assert metrics.metrics_buffer[0].timestamp >= start_time
    
    def test_session_tracking_across_multiple_requests(self):
        """Test session tracking across multiple requests."""
        metrics = BusinessMetrics(enabled=True)
        
        session_id = "test_session_123"
        
        # Simulate multiple requests in the same session
        for i in range(3):
            metrics.track_user_patterns(
                question_category=f"category_{i % 2}",
                complexity="medium",
                session_id=session_id
            )
        
        summary = metrics.get_session_summary(session_id)
        assert summary["question_count"] == 3
        assert summary["unique_categories"] == 2
    
    def test_metrics_buffer_memory_management(self):
        """Test that metrics buffer doesn't grow indefinitely."""
        metrics = BusinessMetrics(enabled=True)
        
        # Add many metrics
        for i in range(100):
            metrics.track_query_success_rate(True, f"test_{i}")
        
        assert len(metrics.metrics_buffer) == 100
        
        # Clear old metrics
        metrics.clear_metrics_buffer(older_than_hours=0)
        
        assert len(metrics.metrics_buffer) == 0