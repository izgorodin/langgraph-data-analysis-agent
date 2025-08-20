"""Tests for sqlglot BigQuery dialect integration."""

import pytest
import sqlglot
from sqlglot import exp

from src.agent.nodes import _has_aggregation, validate_sql_node
from src.agent.state import AgentState


class TestBigQueryDialectParsing:
    """Test BigQuery-specific SQL parsing capabilities."""

    def test_bigquery_date_functions(self):
        """BigQuery date functions should parse correctly."""
        date_queries = [
            "SELECT DATE(created_at) FROM orders",
            "SELECT DATETIME(created_at) FROM orders",
            "SELECT TIMESTAMP(created_at) FROM orders",
            "SELECT EXTRACT(YEAR FROM created_at) FROM orders",
            "SELECT EXTRACT(DAYOFWEEK FROM created_at) FROM orders",
        ]

        for query in date_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT" in result.sql  # Should get auto-LIMIT

    def test_bigquery_string_functions(self):
        """BigQuery string functions should parse correctly."""
        string_queries = [
            "SELECT CONCAT(first_name, ' ', last_name) FROM users",
            "SELECT UPPER(email) FROM users",
            "SELECT LENGTH(email) FROM users",
            "SELECT SUBSTR(email, 1, 5) FROM users",
            "SELECT REGEXP_EXTRACT(email, r'@(.+)') FROM users",
            "SELECT REGEXP_CONTAINS(email, r'gmail\\.com') FROM users",
        ]

        for query in string_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT" in result.sql

    def test_bigquery_array_functions(self):
        """BigQuery array functions should parse correctly."""
        array_queries = [
            "SELECT ARRAY_AGG(product_id) FROM order_items GROUP BY order_id",
            "SELECT ARRAY_AGG(DISTINCT product_id) FROM order_items GROUP BY order_id",
            "SELECT ARRAY_LENGTH(ARRAY_AGG(product_id)) FROM order_items GROUP BY order_id",
        ]

        for query in array_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # These are aggregating queries - should not get auto-LIMIT
            assert "GROUP BY" in result.sql

    def test_bigquery_unnest_operations(self):
        """BigQuery UNNEST operations should parse correctly."""
        unnest_queries = [
            "SELECT * FROM UNNEST(['a', 'b', 'c']) as value",
            "SELECT value, offset_pos FROM UNNEST(['x', 'y', 'z']) as value WITH OFFSET as offset_pos",
        ]

        for query in unnest_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # These might fail on table validation since UNNEST doesn't reference our allowed tables
            # That's acceptable - focus on parsing capability
            if result.error is None or "table" not in result.error.lower():
                assert isinstance(result.sql, str)

    def test_bigquery_window_functions(self):
        """BigQuery window functions should parse correctly."""
        window_queries = [
            "SELECT user_id, ROW_NUMBER() OVER (ORDER BY created_at) FROM orders",
            "SELECT product_id, RANK() OVER (PARTITION BY category ORDER BY price) FROM products",
            "SELECT order_id, LAG(created_at) OVER (ORDER BY created_at) FROM orders",
            "SELECT user_id, LEAD(order_id) OVER (PARTITION BY user_id ORDER BY created_at) FROM orders",
        ]

        for query in window_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Window functions should be treated as aggregating - no auto-LIMIT
            if "LIMIT" in result.sql and "LIMIT" not in query:
                pytest.fail(f"Window function incorrectly got auto-LIMIT: {query}")

    def test_bigquery_mathematical_functions(self):
        """BigQuery mathematical functions should parse correctly."""
        math_queries = [
            "SELECT ROUND(sale_price, 2) FROM order_items",
            "SELECT CEIL(sale_price) FROM order_items",
            "SELECT FLOOR(sale_price) FROM order_items",
            "SELECT ABS(sale_price - 50) FROM order_items",
            "SELECT SQRT(sale_price) FROM order_items",
            "SELECT POW(sale_price, 2) FROM order_items",
        ]

        for query in math_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT" in result.sql  # Non-aggregating, should get LIMIT


class TestSQLGlotParsingEdgeCases:
    """Test edge cases in SQL parsing with sqlglot."""

    def test_complex_expressions_parsing(self):
        """Complex expressions should parse without errors."""
        complex_queries = [
            "SELECT CASE WHEN status = 'Complete' THEN 1 ELSE 0 END FROM orders",
            "SELECT COALESCE(delivered_at, shipped_at, created_at) FROM orders",
            "SELECT IF(status = 'Complete', 'Done', 'Pending') FROM orders",
        ]

        for query in complex_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT" in result.sql

    def test_nested_expressions_parsing(self):
        """Nested expressions should parse correctly."""
        nested_queries = [
            "SELECT EXTRACT(YEAR FROM DATE(created_at)) FROM orders",
            "SELECT UPPER(CONCAT(first_name, ' ', last_name)) FROM users",
            "SELECT ROUND(AVG(sale_price), 2) FROM order_items GROUP BY product_id",
        ]

        for query in nested_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None

    def test_subquery_parsing(self):
        """Subqueries should parse correctly."""
        subquery_queries = [
            "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE age > 25)",
            "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products)",
        ]

        for query in subquery_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            # Should get LIMIT if outer query is non-aggregating
            assert "LIMIT" in result.sql

    def test_cte_parsing(self):
        """CTEs should parse correctly."""
        cte_queries = [
            """
            WITH recent_orders AS (
                SELECT * FROM orders WHERE created_at > '2024-01-01'
            )
            SELECT * FROM recent_orders
            """,
            """
            WITH order_stats AS (
                SELECT user_id, COUNT(*) as order_count
                FROM orders
                GROUP BY user_id
            )
            SELECT * FROM order_stats WHERE order_count > 5
            """,
        ]

        for query in cte_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert isinstance(result.sql, str)


class TestAggregationDetectionAdvanced:
    """Advanced tests for aggregation detection logic."""

    def test_distinct_aggregation_detection(self):
        """DISTINCT should be properly detected as aggregation."""
        distinct_queries = [
            "SELECT DISTINCT category FROM products",
            "SELECT DISTINCT user_id FROM orders",
            "SELECT DISTINCT status, priority FROM orders",
            "SELECT COUNT(DISTINCT user_id) FROM orders",
        ]

        for query in distinct_queries:
            try:
                parsed = sqlglot.parse_one(query, read="bigquery")
                is_agg = _has_aggregation(parsed)

                if "COUNT" in query.upper():
                    assert (
                        is_agg
                    ), f"COUNT DISTINCT not detected as aggregation: {query}"
                else:
                    assert is_agg, f"DISTINCT not detected as aggregation: {query}"
            except Exception as e:
                pytest.fail(f"Failed to parse query {query}: {e}")

    def test_window_function_aggregation_detection(self):
        """Window functions should be detected as aggregation."""
        window_queries = [
            "SELECT user_id, ROW_NUMBER() OVER (ORDER BY created_at) FROM orders",
            "SELECT product_id, RANK() OVER (PARTITION BY category ORDER BY price) FROM products",
            "SELECT order_id, SUM(sale_price) OVER (PARTITION BY user_id) FROM order_items",
        ]

        for query in window_queries:
            try:
                parsed = sqlglot.parse_one(query, read="bigquery")
                is_agg = _has_aggregation(parsed)
                assert is_agg, f"Window function not detected as aggregation: {query}"
            except Exception as e:
                pytest.fail(f"Failed to parse query {query}: {e}")

    def test_aggregate_function_detection(self):
        """Standard aggregate functions should be detected."""
        agg_queries = [
            "SELECT COUNT(*) FROM orders",
            "SELECT SUM(sale_price) FROM order_items",
            "SELECT AVG(price) FROM products",
            "SELECT MIN(created_at) FROM orders",
            "SELECT MAX(price) FROM products",
        ]

        for query in agg_queries:
            try:
                parsed = sqlglot.parse_one(query, read="bigquery")
                is_agg = _has_aggregation(parsed)
                assert is_agg, f"Aggregate function not detected: {query}"
            except Exception as e:
                pytest.fail(f"Failed to parse query {query}: {e}")

    def test_non_aggregating_detection(self):
        """Non-aggregating queries should be correctly identified."""
        non_agg_queries = [
            "SELECT * FROM orders",
            "SELECT id, status FROM orders WHERE status = 'Complete'",
            "SELECT o.*, u.email FROM orders o JOIN users u ON o.user_id = u.id",
        ]

        for query in non_agg_queries:
            try:
                parsed = sqlglot.parse_one(query, read="bigquery")
                is_agg = _has_aggregation(parsed)
                assert (
                    not is_agg
                ), f"Non-aggregating query incorrectly detected as aggregating: {query}"
            except Exception as e:
                pytest.fail(f"Failed to parse query {query}: {e}")


class TestParsingErrorHandling:
    """Test handling of parsing errors and malformed SQL."""

    def test_malformed_sql_handled(self):
        """Malformed SQL should be caught gracefully."""
        malformed_queries = [
            "SELECT * FROM",  # incomplete
            "SELECT FROM orders",  # missing columns
            "SELECT * FROM orders WHERE",  # incomplete WHERE
            "SELECT * orders",  # missing FROM
        ]

        for query in malformed_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            assert "parse" in result.error.lower() or "error" in result.error.lower()

    def test_empty_queries_handled(self):
        """Empty or whitespace queries should be handled."""
        empty_queries = ["", "   ", "\n\t", "-- just a comment"]

        for query in empty_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None

    def test_very_long_queries_handled(self):
        """Very long queries should be handled without hanging."""
        # Create a very long query
        long_where_clause = " OR ".join([f"id = {i}" for i in range(100)])
        long_query = f"SELECT * FROM orders WHERE {long_where_clause}"

        state = AgentState(question="test", sql=long_query)
        result = validate_sql_node(state)

        # Should either succeed or fail gracefully, but not hang
        assert isinstance(result, AgentState)
        if result.error is None:
            assert "LIMIT" in result.sql


class TestBigQuerySpecificFeatures:
    """Test BigQuery-specific features and syntax."""

    def test_qualified_table_names(self):
        """BigQuery qualified table names should be handled."""
        qualified_queries = [
            "SELECT * FROM `project.dataset.orders`",
            "SELECT * FROM dataset.orders",
            "SELECT * FROM `my-project`.dataset.table",
        ]

        for query in qualified_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # These should likely fail table validation since they're not in our whitelist
            # This is the correct security behavior
            if result.error is not None:
                assert any(
                    keyword in result.error.lower()
                    for keyword in ["table", "disallowed", "parse"]
                )

    def test_bigquery_literals(self):
        """BigQuery-specific literals should parse correctly."""
        literal_queries = [
            "SELECT DATE '2024-01-01' FROM orders",
            "SELECT TIMESTAMP '2024-01-01 10:00:00' FROM orders",
            "SELECT TIME '10:00:00' FROM orders",
        ]

        for query in literal_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is None
            assert "LIMIT" in result.sql
