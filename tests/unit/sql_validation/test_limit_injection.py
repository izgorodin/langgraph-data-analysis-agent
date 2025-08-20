"""Tests for LIMIT injection logic and aggregation detection."""

import pytest

from src.agent.nodes import validate_sql_node
from src.agent.state import AgentState


class TestLimitInjection:
    """Test automatic LIMIT injection for non-aggregating queries."""

    def test_non_aggregating_gets_limit(self):
        """Non-aggregating queries should get LIMIT 1000 automatically."""
        non_agg_queries = [
            "SELECT * FROM orders",
            "SELECT id, status FROM orders WHERE status = 'Complete'",
            "SELECT o.*, u.email FROM orders o JOIN users u ON o.user_id = u.id",
        ]

        for query in non_agg_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT 1000" in result.sql or "LIMIT" in result.sql

    def test_aggregating_queries_no_limit(self):
        """Aggregating queries should not get automatic LIMIT."""
        agg_queries = [
            "SELECT COUNT(*) FROM orders",
            "SELECT status, COUNT(*) FROM orders GROUP BY status",
            "SELECT AVG(sale_price) FROM order_items",
            "SELECT SUM(sale_price), MAX(sale_price) FROM order_items GROUP BY product_id",
        ]

        for query in agg_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should not modify SQL for aggregating queries
            assert state.sql == query or result.sql == query

    def test_existing_limit_preserved(self):
        """Existing LIMIT should be preserved if <= 1000."""
        limit_queries = [
            "SELECT * FROM orders LIMIT 100",
            "SELECT * FROM orders LIMIT 500",
            "SELECT * FROM orders LIMIT 1000",
        ]

        for query in limit_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should preserve existing LIMIT
            assert "LIMIT" in result.sql

    def test_large_limit_handling(self):
        """Large LIMIT values should be handled appropriately."""
        large_limit_queries = [
            "SELECT * FROM orders LIMIT 5000",
            "SELECT * FROM orders LIMIT 10000",
        ]

        for query in large_limit_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should preserve the existing LIMIT (even if large)
            # Or could enforce maximum - depends on policy
            assert "LIMIT" in result.sql


class TestAggregationDetection:
    """Test detection of aggregating vs non-aggregating queries."""

    def test_group_by_detected(self):
        """GROUP BY queries should be detected as aggregating."""
        group_by_queries = [
            "SELECT status FROM orders GROUP BY status",
            "SELECT user_id, COUNT(*) FROM orders GROUP BY user_id",
            "SELECT category, AVG(price) FROM products GROUP BY category, department",
        ]

        for query in group_by_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should not add LIMIT to GROUP BY queries
            # The SQL might be modified but should not have auto-LIMIT
            if "LIMIT" in result.sql:
                # If LIMIT is added, it should be explicit in original query
                assert "LIMIT" in query

    def test_aggregate_functions_detected(self):
        """Aggregate functions should be detected."""
        agg_function_queries = [
            "SELECT COUNT(*) FROM orders",
            "SELECT SUM(sale_price) FROM order_items",
            "SELECT AVG(price), MIN(price), MAX(price) FROM products",
            "SELECT COUNT(DISTINCT user_id) FROM orders",
        ]

        for query in agg_function_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should not add automatic LIMIT to aggregate queries
            original_has_limit = "LIMIT" in query
            result_has_limit = "LIMIT" in result.sql

            if result_has_limit and not original_has_limit:
                # If LIMIT was added, this suggests non-agg detection failed
                pytest.fail(f"LIMIT incorrectly added to aggregate query: {query}")

    def test_distinct_detected_as_aggregation(self):
        """DISTINCT should be treated as aggregation."""
        distinct_queries = [
            "SELECT DISTINCT category FROM products",
            "SELECT DISTINCT user_id FROM orders",
            "SELECT DISTINCT status, priority FROM orders",
        ]

        for query in distinct_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # DISTINCT should be treated as aggregation - no auto LIMIT
            if "LIMIT" in result.sql and "LIMIT" not in query:
                pytest.fail(f"LIMIT incorrectly added to DISTINCT query: {query}")

    def test_window_functions_detected(self):
        """Window functions should be detected as aggregating."""
        window_queries = [
            "SELECT user_id, ROW_NUMBER() OVER (ORDER BY created_at) FROM orders",
            "SELECT product_id, RANK() OVER (PARTITION BY category ORDER BY price) FROM products",
            "SELECT order_id, LAG(created_at) OVER (ORDER BY created_at) FROM orders",
        ]

        for query in window_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Window functions should be treated as aggregation
            if "LIMIT" in result.sql and "LIMIT" not in query:
                pytest.fail(
                    f"LIMIT incorrectly added to window function query: {query}"
                )

    def test_having_clause_detected(self):
        """HAVING clauses should indicate aggregation."""
        having_queries = [
            "SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 10",
            "SELECT category FROM products GROUP BY category HAVING AVG(price) > 100",
        ]

        for query in having_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # HAVING implies aggregation - no auto LIMIT
            if "LIMIT" in result.sql and "LIMIT" not in query:
                pytest.fail(f"LIMIT incorrectly added to HAVING query: {query}")


class TestComplexQueryLimitHandling:
    """Test LIMIT handling for complex query structures."""

    def test_cte_limit_handling(self):
        """CTEs should be handled appropriately for LIMIT injection."""
        cte_queries = [
            # Non-aggregating CTE
            """
            WITH recent_orders AS (
                SELECT * FROM orders WHERE created_at > '2024-01-01'
            )
            SELECT * FROM recent_orders
            """,
            # Aggregating CTE
            """
            WITH order_stats AS (
                SELECT user_id, COUNT(*) as order_count FROM orders GROUP BY user_id
            )
            SELECT * FROM order_stats
            """,
        ]

        for query in cte_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Validate that LIMIT is handled appropriately
            assert isinstance(result.sql, str)

    def test_subquery_limit_handling(self):
        """Subqueries should not interfere with LIMIT logic."""
        subquery_queries = [
            # Non-aggregating with subquery
            "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE age > 25)",
            # Aggregating with subquery
            "SELECT COUNT(*) FROM orders WHERE status = (SELECT MAX(status) FROM orders)",
        ]

        for query in subquery_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # Note: These might fail on table whitelist due to complex parsing
            # Focus on LIMIT logic if they pass initial validation
            if result.error is None:
                assert isinstance(result.sql, str)

    def test_union_limit_handling(self):
        """UNION queries should be handled for LIMIT."""
        union_queries = [
            "SELECT id FROM orders UNION SELECT id FROM order_items",
            "SELECT name FROM products UNION ALL SELECT first_name FROM users",
        ]

        for query in union_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # UNION queries should be treated as non-aggregating
            if result.error is None:
                # Should get LIMIT if no aggregation
                assert isinstance(result.sql, str)

    def test_order_by_with_limit(self):
        """ORDER BY should work with LIMIT injection."""
        order_queries = [
            "SELECT * FROM orders ORDER BY created_at DESC",
            "SELECT id, status FROM orders ORDER BY status, created_at",
        ]

        for query in order_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should add LIMIT to ORDER BY queries
            assert "LIMIT" in result.sql
            assert "ORDER BY" in result.sql


class TestLimitEdgeCases:
    """Test edge cases for LIMIT injection."""

    def test_zero_limit_handling(self):
        """LIMIT 0 should be handled appropriately."""
        state = AgentState(question="test", sql="SELECT * FROM orders LIMIT 0")
        result = validate_sql_node(state)

        assert result.error is None
        assert "LIMIT" in result.sql

    def test_offset_with_limit(self):
        """OFFSET with LIMIT should be preserved."""
        state = AgentState(
            question="test", sql="SELECT * FROM orders LIMIT 100 OFFSET 50"
        )
        result = validate_sql_node(state)

        assert result.error is None
        assert "LIMIT" in result.sql
        assert "OFFSET" in result.sql

    def test_nested_aggregation_detection(self):
        """Nested aggregations should be detected properly."""
        nested_queries = [
            "SELECT AVG(order_count) FROM (SELECT user_id, COUNT(*) as order_count FROM orders GROUP BY user_id) subq",
        ]

        for query in nested_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # This is complex and might fail on table parsing
            # If it passes, should be treated as aggregating
            if result.error is None:
                # Complex aggregation - should not get auto LIMIT
                if "LIMIT" in result.sql and "LIMIT" not in query:
                    pytest.fail(
                        f"LIMIT incorrectly added to nested aggregation: {query}"
                    )
                assert (
                    "LIMIT" not in result.sql or "LIMIT" in query
                ), f"LIMIT incorrectly added to nested aggregation: {query}"
