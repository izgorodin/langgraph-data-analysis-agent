#!/usr/bin/env python3
"""
LGDA-009 Error Handling and Recovery Demonstration

This script demonstrates the comprehensive error handling system implemented for LGDA,
including hanging process prevention, graceful degradation, and user-friendly error messages.
"""

import asyncio
import time
from src.error import (
    LGDAError,
    BigQueryExecutionError,
    TimeoutError,
    ErrorClassifier,
    RecoveryEngine,
    TimeoutManager,
    with_timeout
)


async def demonstrate_timeout_prevention():
    """Demonstrate hanging process prevention."""
    print("🔒 Demonstrating Hanging Process Prevention")
    print("=" * 50)
    
    # Create a timeout manager with short timeout for demo
    timeout_manager = TimeoutManager(default_timeout=2)
    
    async def slow_operation():
        print("   Starting slow operation...")
        await asyncio.sleep(5)  # This would hang without timeout
        return "Should not reach here"
    
    try:
        await timeout_manager.with_timeout(
            slow_operation(), 
            timeout=2, 
            operation_name="demo_slow_op"
        )
    except TimeoutError as e:
        print(f"✅ Successfully prevented hanging: {e}")
        print(f"   Error code: {e.error_code}")
        print(f"   Timeout: {e.timeout_seconds}s")
        print(f"   Context: {e.context}")
    
    print()


async def demonstrate_bigquery_array_recovery():
    """Demonstrate BigQuery Array error handling."""
    print("🔧 Demonstrating BigQuery Array Error Recovery")
    print("=" * 50)
    
    engine = RecoveryEngine()
    
    # Simulate BigQuery Array error
    error = BigQueryExecutionError(
        "Array cannot have a null element",
        query="SELECT ARRAY[1, NULL, 3, 4] as numbers",
        job_id="demo_job_123"
    )
    
    recovery = await engine.handle_error(error, context={"operation_id": "demo_array"})
    
    print(f"Original query: {error.query}")
    print(f"Error: {error.message}")
    print(f"Recovery strategy: {recovery.strategy}")
    print(f"Modified query: {recovery.modified_input}")
    print(f"User message: {recovery.user_message}")
    print(f"Should retry: {recovery.should_retry}")
    print()


def demonstrate_user_friendly_messages():
    """Demonstrate user-friendly error messages."""
    print("💬 Demonstrating User-Friendly Error Messages")
    print("=" * 50)
    
    classifier = ErrorClassifier()
    
    # Test various error scenarios
    test_errors = [
        "Permission denied to access table",
        "Array cannot have a null element", 
        "Connection timeout occurred",
        "Rate limit exceeded for API",
        "Table 'customers' not found",
        "SQL syntax error near 'SELEC'",
        "Model 'gpt-4' not available",
        "Out of memory during processing"
    ]
    
    for error_msg in test_errors:
        strategy, severity = classifier.classify(error_msg)
        user_msg = classifier.get_user_message(error_msg)
        is_transient = classifier.is_transient(error_msg)
        
        print(f"Error: {error_msg}")
        print(f"  → Strategy: {strategy.value}")
        print(f"  → Severity: {severity.value}")
        print(f"  → Transient: {is_transient}")
        print(f"  → User message: {user_msg}")
        print()


async def demonstrate_recovery_strategies():
    """Demonstrate different recovery strategies."""
    print("🛠️  Demonstrating Recovery Strategies")
    print("=" * 50)
    
    engine = RecoveryEngine()
    
    # Test scenarios for different recovery strategies
    scenarios = [
        ("Connection timeout", "immediate_retry"),
        ("Rate limit exceeded", "exponential_backoff"),
        ("Model not found", "graceful_degradation"),
        ("SQL syntax error", "user_guided"),
        ("Permission denied", "no_recovery")
    ]
    
    for error_msg, expected_category in scenarios:
        error = Exception(error_msg)
        recovery = await engine.handle_error(error, context={"operation_id": f"demo_{hash(error_msg)}"})
        
        print(f"Error: {error_msg}")
        print(f"  → Strategy: {recovery.strategy}")
        print(f"  → Should retry: {recovery.should_retry}")
        print(f"  → Retry delay: {recovery.retry_delay}s")
        print(f"  → Max retries: {recovery.max_retries}")
        print(f"  → Message: {recovery.message}")
        if recovery.user_message:
            print(f"  → User message: {recovery.user_message}")
        if recovery.modified_input:
            print(f"  → Modified input: {recovery.modified_input}")
        print()


def demonstrate_circuit_breaker():
    """Demonstrate circuit breaker functionality."""
    print("⚡ Demonstrating Circuit Breaker")
    print("=" * 50)
    
    from src.llm.manager import CircuitBreaker
    
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
    
    print(f"Initial state: {breaker.state}")
    print(f"Can execute: {breaker.can_execute()}")
    
    # Simulate failures
    for i in range(5):
        if i < 3:
            breaker.record_failure()
            print(f"Failure {i+1}: state={breaker.state}, can_execute={breaker.can_execute()}")
        elif i == 3:
            print(f"After {breaker.failure_threshold} failures:")
            print(f"  → State: {breaker.state}")
            print(f"  → Can execute: {breaker.can_execute()}")
        else:
            # Simulate success
            breaker.record_success()
            print(f"After success: state={breaker.state}, can_execute={breaker.can_execute()}")
    
    print()


async def demonstrate_end_to_end_scenario():
    """Demonstrate end-to-end error handling scenario."""
    print("🎯 End-to-End Error Handling Scenario")
    print("=" * 50)
    
    print("Scenario: BigQuery query with Array error, followed by timeout on retry")
    
    engine = RecoveryEngine()
    
    # Step 1: Array error
    print("\n1. Initial Array error:")
    array_error = BigQueryExecutionError(
        "Array cannot have a null element",
        query="SELECT ARRAY_AGG(user_id) FROM users WHERE status = 'active'",
        job_id="scenario_job_1"
    )
    
    recovery1 = await engine.handle_error(array_error, context={"operation_id": "scenario_demo"})
    print(f"   Strategy: {recovery1.strategy}")
    print(f"   Modified query: {recovery1.modified_input[:60]}..." if recovery1.modified_input else "   No modification")
    
    # Step 2: Timeout on retry
    print("\n2. Timeout on retry:")
    timeout_error = TimeoutError("Query timed out after 300 seconds", timeout_seconds=300)
    recovery2 = await engine.handle_error(timeout_error, context={"operation_id": "scenario_demo"})
    print(f"   Strategy: {recovery2.strategy}")
    print(f"   Retry delay: {recovery2.retry_delay}s")
    
    # Step 3: Show retry count tracking
    print(f"\n3. Retry count for operation: {engine.get_retry_count('scenario_demo')}")
    
    print("\n✅ Scenario completed - errors handled gracefully without hanging!")
    print()


async def main():
    """Run all demonstrations."""
    print("🚀 LGDA-009: Error Handling and Recovery System Demo")
    print("=" * 60)
    print()
    
    try:
        await demonstrate_timeout_prevention()
        await demonstrate_bigquery_array_recovery()
        demonstrate_user_friendly_messages()
        await demonstrate_recovery_strategies()
        demonstrate_circuit_breaker()
        await demonstrate_end_to_end_scenario()
        
        print("🎉 All demonstrations completed successfully!")
        print("\nKey Features Demonstrated:")
        print("✅ Zero hanging processes (timeout management)")
        print("✅ BigQuery Array error automatic recovery")
        print("✅ User-friendly error messages")
        print("✅ Multiple recovery strategies")
        print("✅ Circuit breaker for cascade failure prevention")
        print("✅ End-to-end error handling flow")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())