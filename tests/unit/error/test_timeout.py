"""Tests for timeout management functionality."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from src.error.timeout import (
    TimeoutManager,
    get_timeout_manager,
    set_timeout_manager,
    with_timeout
)
from src.error.core import TimeoutError


class TestTimeoutManager:
    """Test timeout manager functionality."""
    
    def test_timeout_manager_initialization(self):
        """Test timeout manager initialization."""
        manager = TimeoutManager(default_timeout=60)
        assert manager.default_timeout == 60
        assert manager._active_operations == {}
    
    def test_timeout_manager_default_timeout(self):
        """Test timeout manager with default timeout."""
        manager = TimeoutManager()
        assert manager.default_timeout == 300  # 5 minutes
    
    @pytest.mark.asyncio
    async def test_with_timeout_success(self):
        """Test successful operation with timeout."""
        manager = TimeoutManager(default_timeout=1)
        
        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await manager.with_timeout(fast_operation(), timeout=1)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_with_timeout_failure(self):
        """Test operation that times out."""
        manager = TimeoutManager(default_timeout=1)
        
        async def slow_operation():
            await asyncio.sleep(2)
            return "should not reach here"
        
        with pytest.raises(TimeoutError) as exc_info:
            await manager.with_timeout(slow_operation(), timeout=1, operation_name="slow_op")
        
        error = exc_info.value
        assert error.error_code == "OPERATION_TIMEOUT"
        assert "slow_op" in error.message
        assert error.timeout_seconds == 1
        assert error.operation == "slow_op"
    
    @pytest.mark.asyncio
    async def test_with_timeout_default_timeout(self):
        """Test operation with default timeout."""
        manager = TimeoutManager(default_timeout=1)
        
        async def operation():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await manager.with_timeout(operation())
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_with_timeout_operation_tracking(self):
        """Test that operations are tracked during execution."""
        manager = TimeoutManager(default_timeout=2)
        
        async def tracked_operation():
            # Check that operation is tracked while running
            active_ops = manager.get_active_operations()
            assert "test_op" in active_ops
            await asyncio.sleep(0.1)
            return "success"
        
        result = await manager.with_timeout(tracked_operation(), operation_name="test_op")
        assert result == "success"
        
        # Operation should be removed after completion
        active_ops = manager.get_active_operations()
        assert "test_op" not in active_ops
    
    @pytest.mark.asyncio
    async def test_with_timeout_cleanup_on_timeout(self):
        """Test cleanup when operation times out."""
        manager = TimeoutManager(default_timeout=1)
        
        async def slow_operation():
            await asyncio.sleep(2)
            return "should not reach"
        
        with pytest.raises(TimeoutError):
            await manager.with_timeout(slow_operation(), operation_name="cleanup_test")
        
        # Operation should be cleaned up after timeout
        active_ops = manager.get_active_operations()
        assert "cleanup_test" not in active_ops
    
    def test_with_timeout_sync_decorator(self):
        """Test synchronous timeout decorator."""
        manager = TimeoutManager(default_timeout=1)
        
        @manager.with_timeout_sync(timeout=2)
        def fast_sync_operation():
            time.sleep(0.1)
            return "sync_success"
        
        result = fast_sync_operation()
        assert result == "sync_success"
    
    def test_with_timeout_sync_decorator_timeout(self):
        """Test synchronous timeout decorator with timeout."""
        manager = TimeoutManager(default_timeout=1)
        
        @manager.with_timeout_sync(timeout=1)
        def slow_sync_operation():
            time.sleep(2)
            return "should not reach"
        
        with pytest.raises(TimeoutError) as exc_info:
            slow_sync_operation()
        
        error = exc_info.value
        assert error.error_code == "OPERATION_TIMEOUT"
        assert "exceeded timeout" in error.message
    
    def test_get_active_operations(self):
        """Test getting active operations."""
        manager = TimeoutManager()
        
        # Initially empty
        active_ops = manager.get_active_operations()
        assert active_ops == {}
        
        # Add some operations manually for testing
        manager._active_operations["op1"] = time.time()
        manager._active_operations["op2"] = time.time() - 100
        
        active_ops = manager.get_active_operations()
        assert "op1" in active_ops
        assert "op2" in active_ops
        assert len(active_ops) == 2
    
    def test_is_operation_timeout_likely(self):
        """Test timeout likelihood detection."""
        manager = TimeoutManager(default_timeout=100)
        
        # Operation that just started
        manager._active_operations["new_op"] = time.time()
        assert manager.is_operation_timeout_likely("new_op") is False
        
        # Operation that's been running for 90% of timeout
        manager._active_operations["old_op"] = time.time() - 90
        assert manager.is_operation_timeout_likely("old_op") is True
        
        # Non-existent operation
        assert manager.is_operation_timeout_likely("nonexistent") is False
    
    def test_is_operation_timeout_likely_custom_threshold(self):
        """Test timeout likelihood with custom threshold."""
        manager = TimeoutManager(default_timeout=100)
        
        # Operation running for 50% of timeout
        manager._active_operations["half_op"] = time.time() - 50
        
        # With 40% threshold, should be likely
        assert manager.is_operation_timeout_likely("half_op", threshold=0.4) is True
        
        # With 60% threshold, should not be likely
        assert manager.is_operation_timeout_likely("half_op", threshold=0.6) is False


class TestGlobalTimeoutManager:
    """Test global timeout manager functions."""
    
    def test_get_timeout_manager_singleton(self):
        """Test that get_timeout_manager returns singleton."""
        manager1 = get_timeout_manager()
        manager2 = get_timeout_manager()
        assert manager1 is manager2
    
    def test_set_timeout_manager(self):
        """Test setting custom timeout manager."""
        original_manager = get_timeout_manager()
        custom_manager = TimeoutManager(default_timeout=42)
        
        set_timeout_manager(custom_manager)
        current_manager = get_timeout_manager()
        
        assert current_manager is custom_manager
        assert current_manager.default_timeout == 42
        
        # Reset to original for other tests
        set_timeout_manager(original_manager)
    
    @pytest.mark.asyncio
    async def test_with_timeout_convenience_function(self):
        """Test convenience with_timeout function."""
        async def test_operation():
            await asyncio.sleep(0.1)
            return "convenience_success"
        
        result = await with_timeout(test_operation(), timeout=1, operation_name="convenience_test")
        assert result == "convenience_success"
    
    @pytest.mark.asyncio
    async def test_with_timeout_convenience_function_timeout(self):
        """Test convenience with_timeout function with timeout."""
        async def slow_operation():
            await asyncio.sleep(2)
            return "should not reach"
        
        with pytest.raises(TimeoutError):
            await with_timeout(slow_operation(), timeout=1, operation_name="convenience_timeout")


class TestTimeoutErrorHandling:
    """Test timeout error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_timeout_error_context(self):
        """Test that timeout errors contain proper context."""
        manager = TimeoutManager(default_timeout=1)
        
        async def operation_with_context():
            await asyncio.sleep(2)
            return "should timeout"
        
        with pytest.raises(TimeoutError) as exc_info:
            await manager.with_timeout(
                operation_with_context(), 
                timeout=1, 
                operation_name="context_test"
            )
        
        error = exc_info.value
        assert error.context["timeout"] == 1
        assert error.context["operation"] == "context_test"
        assert "elapsed" in error.context
        assert error.context["elapsed"] >= 1
    
    @pytest.mark.asyncio
    async def test_nested_timeout_operations(self):
        """Test nested timeout operations."""
        manager = TimeoutManager(default_timeout=2)
        
        async def outer_operation():
            async def inner_operation():
                await asyncio.sleep(0.1)
                return "inner_success"
            
            result = await manager.with_timeout(
                inner_operation(), 
                timeout=1, 
                operation_name="inner_op"
            )
            return f"outer_{result}"
        
        result = await manager.with_timeout(
            outer_operation(), 
            timeout=2, 
            operation_name="outer_op"
        )
        assert result == "outer_inner_success"
    
    @pytest.mark.asyncio
    async def test_concurrent_timeout_operations(self):
        """Test concurrent operations with timeouts."""
        manager = TimeoutManager(default_timeout=2)
        
        async def concurrent_operation(op_id, delay):
            await asyncio.sleep(delay)
            return f"result_{op_id}"
        
        # Run multiple operations concurrently
        tasks = [
            manager.with_timeout(
                concurrent_operation(i, 0.1), 
                timeout=1, 
                operation_name=f"concurrent_op_{i}"
            )
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        expected = [f"result_{i}" for i in range(3)]
        assert results == expected