"""Timeout management for preventing hanging processes."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Awaitable, Callable, Optional, TypeVar

from .core import TimeoutError

T = TypeVar("T")


class TimeoutManager:
    """Manages operation timeouts to prevent hanging processes."""

    def __init__(self, default_timeout: int = 300):
        """
        Initialize timeout manager.

        Args:
            default_timeout: Default timeout in seconds (5 minutes)
        """
        self.default_timeout = default_timeout
        self._active_operations: dict[str, float] = {}

    async def with_timeout(
        self,
        operation: Awaitable[T],
        timeout: Optional[int] = None,
        operation_name: Optional[str] = None,
    ) -> T:
        """
        Execute operation with guaranteed timeout.

        Args:
            operation: Async operation to execute
            timeout: Timeout in seconds (uses default if None)
            operation_name: Name for tracking and logging

        Returns:
            Operation result

        Raises:
            TimeoutError: If operation times out
        """
        timeout = timeout or self.default_timeout
        operation_name = operation_name or "unknown_operation"

        start_time = time.time()
        self._active_operations[operation_name] = start_time

        try:
            result = await asyncio.wait_for(operation, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Force cleanup and raise appropriate error
            await self._force_cleanup(operation_name)
            raise TimeoutError(
                f"Operation '{operation_name}' timed out after {timeout}s",
                context={
                    "timeout": timeout,
                    "operation": operation_name,
                    "elapsed": time.time() - start_time,
                },
                timeout_seconds=timeout,
                operation=operation_name,
            )
        finally:
            self._active_operations.pop(operation_name, None)

    def with_timeout_sync(
        self, timeout: Optional[int] = None, operation_name: Optional[str] = None
    ):
        """
        Decorator for synchronous functions with timeout.

        Args:
            timeout: Timeout in seconds
            operation_name: Name for tracking

        Returns:
            Decorated function
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                timeout_val = timeout or self.default_timeout
                op_name = operation_name or func.__name__

                start_time = time.time()
                self._active_operations[op_name] = start_time

                try:
                    # For sync functions, we can't enforce hard timeout
                    # but we can track execution time
                    result = func(*args, **kwargs)

                    elapsed = time.time() - start_time
                    if elapsed > timeout_val:
                        raise TimeoutError(
                            f"Synchronous operation '{op_name}' exceeded timeout ({elapsed:.1f}s > {timeout_val}s)",
                            context={
                                "timeout": timeout_val,
                                "operation": op_name,
                                "elapsed": elapsed,
                            },
                            timeout_seconds=timeout_val,
                            operation=op_name,
                        )

                    return result
                finally:
                    self._active_operations.pop(op_name, None)

            return wrapper

        return decorator

    async def _force_cleanup(self, operation_name: str) -> None:
        """
        Force cleanup of timed-out operation.

        Args:
            operation_name: Name of operation to clean up
        """
        # Log the timeout for monitoring
        start_time = self._active_operations.get(operation_name, time.time())
        elapsed = time.time() - start_time

        # TODO: Add actual cleanup logic based on operation type
        # For now, just log the timeout
        print(f"TIMEOUT: Operation '{operation_name}' timed out after {elapsed:.1f}s")

    def get_active_operations(self) -> dict[str, float]:
        """
        Get currently active operations and their start times.

        Returns:
            Dictionary mapping operation names to start times
        """
        return self._active_operations.copy()

    def is_operation_timeout_likely(
        self, operation_name: str, threshold: float = 0.8
    ) -> bool:
        """
        Check if an operation is likely to timeout soon.

        Args:
            operation_name: Name of operation to check
            threshold: Threshold percentage of timeout (0.8 = 80%)

        Returns:
            True if operation is likely to timeout soon
        """
        start_time = self._active_operations.get(operation_name)
        if not start_time:
            return False

        elapsed = time.time() - start_time
        return elapsed > (self.default_timeout * threshold)


# Global timeout manager instance
_default_timeout_manager: Optional[TimeoutManager] = None


def get_timeout_manager() -> TimeoutManager:
    """Get or create the default timeout manager."""
    global _default_timeout_manager
    if _default_timeout_manager is None:
        _default_timeout_manager = TimeoutManager()
    return _default_timeout_manager


def set_timeout_manager(manager: TimeoutManager) -> None:
    """Set the default timeout manager."""
    global _default_timeout_manager
    _default_timeout_manager = manager


# Convenience function for common timeout usage
async def with_timeout(
    operation: Awaitable[T],
    timeout: Optional[int] = None,
    operation_name: Optional[str] = None,
) -> T:
    """
    Execute operation with timeout using default timeout manager.

    Args:
        operation: Async operation to execute
        timeout: Timeout in seconds
        operation_name: Name for tracking

    Returns:
        Operation result
    """
    manager = get_timeout_manager()
    return await manager.with_timeout(operation, timeout, operation_name)
