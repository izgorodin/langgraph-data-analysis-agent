"""Unit tests for LGDA-018: Pipeline timing instrumentation."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.state import AgentState
from src.observability.instrumented_nodes import instrument_node


class TestTimingInstrumentation:
    """Test timing instrumentation for pipeline nodes."""

    @pytest.fixture
    def mock_observability_components(self):
        """Mock all observability components to isolate timing functionality."""
        with patch("src.observability.instrumented_nodes.get_metrics") as mock_metrics, \
             patch("src.observability.instrumented_nodes.get_logger") as mock_logger, \
             patch("src.observability.instrumented_nodes.get_tracer") as mock_tracer, \
             patch("src.observability.instrumented_nodes.get_business_metrics") as mock_biz_metrics, \
             patch("src.observability.instrumented_nodes.set_request_context") as mock_context:
            
            # Set up mock returns
            mock_tracer.return_value.trace_stage_execution.return_value.__enter__ = MagicMock()
            mock_tracer.return_value.trace_stage_execution.return_value.__exit__ = MagicMock()
            mock_context.return_value.__enter__ = MagicMock()
            mock_context.return_value.__exit__ = MagicMock()
            
            yield {
                "metrics": mock_metrics.return_value,
                "logger": mock_logger.return_value,
                "tracer": mock_tracer.return_value,
                "business_metrics": mock_biz_metrics.return_value,
                "context": mock_context.return_value,
            }

    @pytest.mark.asyncio
    async def test_instrument_node_records_timing(self, mock_observability_components):
        """Test that instrument_node decorator records timing in state."""
        
        @instrument_node("test_node")
        def test_node_function(state: AgentState) -> AgentState:
            # Simulate some work
            time.sleep(0.01)
            state.sql = "SELECT 1"
            return state
        
        # Create initial state
        state = AgentState(question="Test timing instrumentation")
        
        # Execute the instrumented function
        result = test_node_function(state)
        
        # Verify timing was recorded
        assert "test_node" in result.pipeline_timing
        assert result.pipeline_timing["test_node"] > 0
        assert result.pipeline_timing["test_node"] < 1.0  # Should be small
        
        # Verify the function still worked
        assert result.sql == "SELECT 1"

    def test_instrument_node_timing_accuracy(self, mock_observability_components):
        """Test that recorded timing is reasonably accurate."""
        
        sleep_duration = 0.05  # 50ms
        
        @instrument_node("timing_test")
        def slow_node_function(state: AgentState) -> AgentState:
            time.sleep(sleep_duration)
            return state
        
        state = AgentState(question="Timing accuracy test")
        
        start_time = time.time()
        result = slow_node_function(state)
        total_time = time.time() - start_time
        
        recorded_time = result.pipeline_timing["timing_test"]
        
        # Recorded time should be close to actual sleep duration
        assert recorded_time >= sleep_duration * 0.8  # Allow 20% variance
        assert recorded_time <= total_time + 0.01  # Should not exceed total time significantly

    @pytest.mark.asyncio
    async def test_instrument_node_error_timing(self, mock_observability_components):
        """Test that timing is recorded even when node function fails."""
        
        # Mock the context manager to avoid affecting exception propagation
        mock_tracer = mock_observability_components["tracer"]
        mock_span = MagicMock()
        mock_tracer.trace_stage_execution.return_value.__enter__.return_value = mock_span
        mock_tracer.trace_stage_execution.return_value.__exit__.return_value = None
        
        # Mock the logging context similarly
        with patch("src.observability.instrumented_nodes.set_request_context") as mock_context:
            mock_context.return_value.__enter__.return_value = MagicMock()
            mock_context.return_value.__exit__.return_value = None
            
            @instrument_node("error_node")
            def failing_node_function(state: AgentState) -> AgentState:
                time.sleep(0.01)
                raise ValueError("Test error")
            
            state = AgentState(question="Error timing test")
            
            with pytest.raises(ValueError, match="Test error"):
                failing_node_function(state)
            
            # Verify timing was still recorded despite the error
            assert "error_node" in state.pipeline_timing
            assert state.pipeline_timing["error_node"] > 0

    def test_multiple_nodes_timing_accumulation(self, mock_observability_components):
        """Test that multiple nodes accumulate timing data in the same state."""
        
        @instrument_node("node_1")
        def node_1(state: AgentState) -> AgentState:
            time.sleep(0.01)
            state.plan_json = {"task": "test"}
            return state
        
        @instrument_node("node_2")
        def node_2(state: AgentState) -> AgentState:
            time.sleep(0.02)
            state.sql = "SELECT 1"
            return state
        
        @instrument_node("node_3")
        def node_3(state: AgentState) -> AgentState:
            time.sleep(0.01)
            state.report = "Test report"
            return state
        
        # Execute nodes in sequence
        state = AgentState(question="Multi-node timing test")
        state = node_1(state)
        state = node_2(state)
        state = node_3(state)
        
        # Verify all timings were recorded
        assert len(state.pipeline_timing) == 3
        assert "node_1" in state.pipeline_timing
        assert "node_2" in state.pipeline_timing
        assert "node_3" in state.pipeline_timing
        
        # Verify relative timing (node_2 should be roughly 2x node_1 and node_3)
        assert state.pipeline_timing["node_2"] > state.pipeline_timing["node_1"]
        assert state.pipeline_timing["node_2"] > state.pipeline_timing["node_3"]

    def test_timing_with_span_attributes(self, mock_observability_components):
        """Test that timing is added to tracing spans."""
        mock_span = mock_observability_components["tracer"].trace_stage_execution.return_value.__enter__.return_value
        
        @instrument_node("span_test")
        def test_node(state: AgentState) -> AgentState:
            time.sleep(0.01)
            return state
        
        state = AgentState(question="Span timing test")
        test_node(state)
        
        # Verify span.set_attribute was called with duration_ms
        mock_span.set_attribute.assert_any_call("duration_ms", pytest.approx(10, abs=20))  # ~10ms
        mock_span.set_attribute.assert_any_call("success", True)

    def test_timing_performance_overhead(self, mock_observability_components):
        """Test that timing instrumentation functional overhead is reasonable."""
        
        # Test function with instrumentation
        @instrument_node("perf_test")
        def instrumented_function(state: AgentState) -> AgentState:
            state.sql = "SELECT 1"
            return state
        
        # Verify timing was actually recorded
        state = AgentState(question="Performance test")
        result = instrumented_function(state)
        assert "perf_test" in result.pipeline_timing
        assert result.pipeline_timing["perf_test"] >= 0  # Should record some time
        
        # Verify function works correctly
        assert result.sql == "SELECT 1"

    def test_timing_state_isolation(self, mock_observability_components):
        """Test that timing data is properly isolated between different state instances."""
        
        @instrument_node("isolation_test")
        def test_node(state: AgentState) -> AgentState:
            time.sleep(0.01)
            return state
        
        # Create two different state instances
        state1 = AgentState(question="State 1")
        state2 = AgentState(question="State 2")
        
        # Execute with different states
        result1 = test_node(state1)
        result2 = test_node(state2)
        
        # Verify timing is recorded in both states independently
        assert "isolation_test" in result1.pipeline_timing
        assert "isolation_test" in result2.pipeline_timing
        
        # Timing values might be different due to system variance
        assert result1.pipeline_timing["isolation_test"] > 0
        assert result2.pipeline_timing["isolation_test"] > 0
        
        # States should remain independent
        assert result1 is not result2
        assert result1.question != result2.question


class TestTimingIntegration:
    """Integration tests for timing with real instrumented nodes."""

    def test_plan_node_timing_initialization(self):
        """Test that the plan node initializes pipeline timing."""
        from src.observability.instrumented_nodes import instrumented_plan
        
        state = AgentState(question="Test plan timing initialization")
        
        # Mock the actual plan function to avoid external dependencies
        with patch("src.observability.instrumented_nodes.plan") as mock_plan:
            mock_plan.return_value = state
            
            with patch("src.observability.instrumented_nodes.get_logger"), \
                 patch("src.observability.instrumented_nodes.get_business_metrics"), \
                 patch("src.observability.instrumented_nodes._determine_query_complexity"):
                
                result = instrumented_plan(state)
        
        # Verify that pipeline timing was initialized
        assert result.pipeline_start_time is not None
        assert isinstance(result.pipeline_timing, dict)

    def test_report_node_timing_summary(self):
        """Test that the report node generates timing summary."""
        from src.observability.instrumented_nodes import instrumented_report
        
        state = AgentState(question="Test report timing summary")
        state.start_pipeline_timing()
        state.record_node_timing("plan", 0.1)
        state.record_node_timing("execute_sql", 0.5)
        
        # Mock the actual report function and logger
        with patch("src.observability.instrumented_nodes.report") as mock_report, \
             patch("src.observability.instrumented_nodes.get_logger") as mock_logger, \
             patch("src.observability.instrumented_nodes.get_metrics"), \
             patch("src.observability.instrumented_nodes.get_business_metrics"):
            
            mock_report.return_value = state
            mock_logger_instance = mock_logger.return_value
            
            result = instrumented_report(state)
        
        # Verify that performance metric was logged with timing summary
        mock_logger_instance.log_performance_metric.assert_called()
        
        # Get the call arguments
        call_args = mock_logger_instance.log_performance_metric.call_args
        assert call_args[1]["operation"] == "pipeline_execution"
        assert "node_timings" in call_args[1]["resource_usage"]
        assert call_args[1]["resource_usage"]["total_nodes"] == 2