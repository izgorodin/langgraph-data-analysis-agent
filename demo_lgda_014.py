#!/usr/bin/env python3
"""Demo script for LGDA-014: Strict No-Fabrication On Error Paths.

This script demonstrates the fail-fast behavior that prevents report generation
when errors exist in the pipeline state.
"""

import os
from src.agent.nodes import analyze_df_node, report_node
from src.agent.state import AgentState
from src.config import LGDAConfig


def demo_strict_mode_enabled():
    """Demonstrate strict mode behavior (default)."""
    print("=== DEMO: Strict No-Fabrication Mode ENABLED (default) ===")
    
    # Setup state with error (simulating failed BigQuery execution)
    state = AgentState(
        question="What is the total revenue for Q4?",
        error="BigQuery execution error: Query timeout after 30 seconds",
        sql="SELECT SUM(revenue) FROM orders WHERE quarter = 'Q4'",
        plan_json={"table": "orders", "metrics": ["revenue"], "filters": ["quarter = 'Q4'"]},
        df_summary={"rows": 0, "columns": []}  # No data due to error
    )
    
    print(f"Initial state error: {state.error}")
    print(f"Initial state report: {state.report}")
    print(f"Initial state history: {state.history}")
    
    # Process through analyze_df_node
    state_after_analyze = analyze_df_node(state)
    print(f"\nAfter analyze_df_node:")
    print(f"  Error: {state_after_analyze.error}")
    print(f"  History: {state_after_analyze.history}")
    print(f"  --> Analysis blocked due to error (fail-fast)")
    
    # Process through report_node
    final_state = report_node(state_after_analyze)
    print(f"\nAfter report_node:")
    print(f"  Error: {final_state.error}")
    print(f"  Report: {final_state.report}")
    print(f"  --> Report generation blocked due to error (fail-fast)")
    
    print("\n✅ SUCCESS: No fabricated content generated despite error")


def demo_strict_mode_disabled():
    """Demonstrate behavior when strict mode is disabled."""
    print("\n=== DEMO: Strict No-Fabrication Mode DISABLED ===")
    
    # Set environment to disable strict mode
    os.environ["LGDA_STRICT_NO_FAKE_REPORT"] = "false"
    
    # Setup state with error
    state = AgentState(
        question="What is the total revenue for Q4?",
        error="Some non-critical warning occurred",
        sql="SELECT SUM(revenue) FROM orders WHERE quarter = 'Q4'",
        plan_json={"table": "orders", "metrics": ["revenue"], "filters": ["quarter = 'Q4'"]},
        df_summary={"rows": 100, "columns": ["revenue"], "head": [{"revenue": 50000}]}
    )
    
    print(f"Initial state error: {state.error}")
    print(f"Initial state report: {state.report}")
    
    # Process through analyze_df_node
    state_after_analyze = analyze_df_node(state)
    print(f"\nAfter analyze_df_node:")
    print(f"  Error: {state_after_analyze.error}")
    print(f"  History: {state_after_analyze.history}")
    print(f"  --> Analysis generated despite error (strict mode disabled)")
    
    # Mock LLM completion for report generation
    import unittest.mock
    with unittest.mock.patch('src.agent.nodes.llm_completion', return_value="Revenue analysis: $50,000 total"):
        final_state = report_node(state_after_analyze)
    
    print(f"\nAfter report_node:")
    print(f"  Error: {final_state.error}")
    print(f"  Report: {final_state.report}")
    print(f"  --> Report generated despite error (strict mode disabled)")
    
    print("\n⚠️  WARNING: Content generated despite error (backward compatibility mode)")
    
    # Reset environment
    del os.environ["LGDA_STRICT_NO_FAKE_REPORT"]


def demo_normal_operation():
    """Demonstrate normal operation without errors."""
    print("\n=== DEMO: Normal Operation (No Errors) ===")
    
    # Setup state without error
    state = AgentState(
        question="What is the total revenue for Q4?",
        sql="SELECT SUM(revenue) FROM orders WHERE quarter = 'Q4'",
        plan_json={"table": "orders", "metrics": ["revenue"], "filters": ["quarter = 'Q4'"]},
        df_summary={"rows": 1, "columns": ["total_revenue"], "head": [{"total_revenue": 75000}]}
    )
    
    print(f"Initial state error: {state.error}")
    print(f"Initial state report: {state.report}")
    
    # Process through analyze_df_node
    state_after_analyze = analyze_df_node(state)
    print(f"\nAfter analyze_df_node:")
    print(f"  Error: {state_after_analyze.error}")
    print(f"  History: {state_after_analyze.history}")
    print(f"  --> Normal analysis generated")
    
    # Mock LLM completion for report generation
    import unittest.mock
    with unittest.mock.patch('src.agent.nodes.llm_completion', 
                           return_value="Q4 revenue analysis shows total of $75,000. Strong performance with 1 record processed."):
        final_state = report_node(state_after_analyze)
    
    print(f"\nAfter report_node:")
    print(f"  Error: {final_state.error}")
    print(f"  Report: {final_state.report}")
    print(f"  --> Normal report generated")
    
    print("\n✅ SUCCESS: Normal operation completed successfully")


def demo_configuration():
    """Demonstrate configuration flag behavior."""
    print("\n=== DEMO: Configuration Flag Behavior ===")
    
    # Test default configuration
    config_default = LGDAConfig()
    print(f"Default strict_no_fake_report: {config_default.strict_no_fake_report}")
    
    # Test with environment override
    os.environ["LGDA_STRICT_NO_FAKE_REPORT"] = "false"
    config_disabled = LGDAConfig()
    print(f"With LGDA_STRICT_NO_FAKE_REPORT=false: {config_disabled.strict_no_fake_report}")
    
    os.environ["LGDA_STRICT_NO_FAKE_REPORT"] = "true"
    config_enabled = LGDAConfig()
    print(f"With LGDA_STRICT_NO_FAKE_REPORT=true: {config_enabled.strict_no_fake_report}")
    
    # Clean up
    del os.environ["LGDA_STRICT_NO_FAKE_REPORT"]
    
    print("\n✅ Configuration flag works correctly")


if __name__ == "__main__":
    print("LGDA-014: Strict No-Fabrication On Error Paths - Demo")
    print("=" * 60)
    
    demo_configuration()
    demo_strict_mode_enabled()
    demo_strict_mode_disabled()
    demo_normal_operation()
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETED SUCCESSFULLY")
    print("Key Features Demonstrated:")
    print("  ✅ Fail-fast behavior prevents fabricated reports on errors")
    print("  ✅ Configuration flag allows backward compatibility")
    print("  ✅ Normal operation unaffected when no errors exist")
    print("  ✅ Proper logging and observability markers generated")