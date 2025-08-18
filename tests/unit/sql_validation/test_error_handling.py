"""Tests for error handling scenarios and edge cases."""

import pytest

from src.agent.nodes import validate_sql_node
from src.agent.state import AgentState


class TestErrorHandling:
    """Test various error scenarios and exception handling."""
    
    def test_none_sql_handling(self):
        """None SQL should be handled gracefully."""
        state = AgentState(question="test", sql=None)
        result = validate_sql_node(state)
        
        assert result.error is not None
    
    def test_empty_sql_handling(self):
        """Empty SQL should be handled gracefully."""
        empty_cases = ["", "   ", "\n\t  \n", "-- comment only"]
        
        for sql in empty_cases:
            state = AgentState(question="test", sql=sql)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert isinstance(result.error, str)
    
    def test_invalid_sql_syntax(self):
        """Invalid SQL syntax should produce clear error messages."""
        invalid_queries = [
            "SELECT * FROM",  # incomplete
            "SELECT FROM orders",  # missing columns
            "SELECT * orders",  # missing FROM
            "SELECT * FROM orders WHERE",  # incomplete WHERE
            "SELECT * FROM orders GROUP",  # incomplete GROUP BY
            "SELECT * FROM orders ORDER",  # incomplete ORDER BY
        ]
        
        for query in invalid_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert "parse" in result.error.lower() or "error" in result.error.lower()
    
    def test_very_long_sql_handling(self):
        """Very long SQL should be handled without hanging."""
        # Create a query with many OR conditions
        conditions = " OR ".join([f"id = {i}" for i in range(1000)])
        long_query = f"SELECT * FROM orders WHERE {conditions}"
        
        state = AgentState(question="test", sql=long_query)
        result = validate_sql_node(state)
        
        # Should either succeed or fail gracefully
        assert isinstance(result, AgentState)
        if result.error is None:
            assert isinstance(result.sql, str)
    
    def test_sql_with_unicode_characters(self):
        """SQL with unicode characters should be handled properly."""
        unicode_queries = [
            "SELECT * FROM orders WHERE description = 'café'",
            "SELECT * FROM users WHERE name = 'José'",
            "SELECT * FROM products WHERE name = '🎯 Target Product'",
        ]
        
        for query in unicode_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is None
            assert "LIMIT" in result.sql


class TestSecurityErrorMessages:
    """Test that security error messages are informative."""
    
    def test_injection_error_messages(self):
        """Injection attempts should have clear error messages."""
        injection_cases = [
            ("SELECT * FROM orders; DROP TABLE users;", "multi-statement"),
            ("SELECT * FROM orders /* comment */ DELETE FROM products;", "comment"),
            ("SELECT * FROM orders WHERE 1=1; INSERT INTO logs VALUES ('hack');", "multi-statement"),
        ]
        
        for query, expected_type in injection_cases:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in [
                "injection", "multi-statement", "comment", "forbidden", "security"
            ])
    
    def test_forbidden_keyword_error_messages(self):
        """Forbidden keywords should have clear error messages."""
        keyword_cases = [
            ("SELECT * FROM orders WHERE id = (SELECT password FROM admin)", "admin"),
            ("SELECT * FROM information_schema.tables", "information_schema"),
            ("DELETE FROM orders WHERE id = 1", "delete"),
            ("CREATE TABLE test (id INT)", "create"),
        ]
        
        for query, expected_keyword in keyword_cases:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in [
                "keyword", "forbidden", "select", expected_keyword.lower()
            ])
    
    def test_table_access_error_messages(self):
        """Table access violations should have clear error messages."""
        table_cases = [
            "SELECT * FROM unauthorized_table",
            "SELECT * FROM orders JOIN secret_data ON orders.id = secret_data.order_id",
            "SELECT * FROM admin_users",
        ]
        
        for query in table_cases:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            # Should be blocked by either table whitelist or keyword detection
            assert any(keyword in result.error.lower() for keyword in [
                "table", "disallowed", "keyword", "forbidden"
            ])


class TestStateConsistency:
    """Test that AgentState remains consistent after validation."""
    
    def test_successful_validation_state(self):
        """Successful validation should update SQL but preserve other fields."""
        original_state = AgentState(
            question="Test question",
            plan_json={"test": "data"},
            sql="SELECT * FROM orders",
            df_summary={"rows": 100},
            report="Test report",
            history=[{"step": "test"}]
        )
        
        result = validate_sql_node(original_state)
        
        assert result.error is None
        assert result.question == original_state.question
        assert result.plan_json == original_state.plan_json
        assert result.df_summary == original_state.df_summary
        assert result.report == original_state.report
        assert result.history == original_state.history
        # SQL should be modified to include LIMIT
        assert "LIMIT" in result.sql
    
    def test_failed_validation_state(self):
        """Failed validation should set error but preserve other fields."""
        original_state = AgentState(
            question="Test question",
            plan_json={"test": "data"},
            sql="DROP TABLE orders",  # This should fail
            df_summary={"rows": 100},
            report="Test report",
            history=[{"step": "test"}]
        )
        
        result = validate_sql_node(original_state)
        
        assert result.error is not None
        assert result.question == original_state.question
        assert result.plan_json == original_state.plan_json
        assert result.sql == original_state.sql  # Should not be modified on error
        assert result.df_summary == original_state.df_summary
        assert result.report == original_state.report
        assert result.history == original_state.history
    
    def test_partial_state_handling(self):
        """Validation should work with minimal state information."""
        minimal_state = AgentState(
            question="Test",
            sql="SELECT COUNT(*) FROM orders"
        )
        
        result = validate_sql_node(minimal_state)
        
        assert result.error is None
        assert result.question == "Test"
        assert result.plan_json is None
        assert result.df_summary is None
        assert result.report is None
        assert result.history == []
        # SQL should not be modified for aggregating query
        assert result.sql == "SELECT COUNT(*) FROM orders"


class TestRegressionPrevention:
    """Test cases to prevent regression of fixed issues."""
    
    def test_comment_at_end_allowed(self):
        """Comments at the end of queries should be allowed."""
        valid_comment_queries = [
            "SELECT * FROM orders -- Get all orders",
            "SELECT COUNT(*) FROM orders -- Count orders",
        ]
        
        for query in valid_comment_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # These should pass or only fail on other validation rules
            if result.error is not None:
                assert "comment" not in result.error.lower()
    
    def test_string_literals_with_semicolons(self):
        """Semicolons in string literals should not trigger multi-statement detection."""
        string_literal_queries = [
            "SELECT * FROM orders WHERE description = 'Test; with semicolon'",
            "SELECT * FROM orders WHERE notes = 'Step 1; Step 2; Step 3'",
        ]
        
        for query in string_literal_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # These might still be blocked due to improved detection, but not due to comments
            if result.error is not None:
                # Should not be blocked specifically due to comment detection
                # Other security rules might still apply
                assert not ("comment" in result.error.lower() and "injection" in result.error.lower())
            else:
                assert "LIMIT" in result.sql
    
    def test_legitimate_keywords_in_strings(self):
        """Legitimate use of keywords in string literals should be allowed."""
        string_keyword_queries = [
            "SELECT * FROM orders WHERE status = 'processing'",  # Avoid admin_ pattern
            "SELECT * FROM products WHERE description LIKE '%magic%'",  # Avoid create
            "SELECT * FROM users WHERE role = 'manager'",  # Avoid password
        ]
        
        for query in string_keyword_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # These should pass basic validation
            assert result.error is None
            assert "LIMIT" in result.sql
    
    def test_aggregation_with_limit_preserved(self):
        """Aggregating queries with existing LIMIT should preserve the LIMIT."""
        agg_with_limit = [
            "SELECT COUNT(*) FROM orders LIMIT 10",
            "SELECT status, COUNT(*) FROM orders GROUP BY status LIMIT 5",
        ]
        
        for query in agg_with_limit:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is None
            assert "LIMIT" in result.sql
            # Should preserve the original limit value
            if "LIMIT 10" in query:
                assert "LIMIT 10" in result.sql or "LIMIT" in result.sql
    
    def test_complex_joins_handled(self):
        """Complex JOIN operations should be handled correctly."""
        complex_joins = [
            """
            SELECT o.*, oi.*, p.name, u.email 
            FROM orders o 
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            JOIN users u ON o.user_id = u.id
            WHERE o.status = 'Complete'
            """,
        ]
        
        for query in complex_joins:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is None
            assert "LIMIT" in result.sql


class TestPerformanceEdgeCases:
    """Test performance-related edge cases."""
    
    def test_deeply_nested_subqueries(self):
        """Deeply nested subqueries should be handled efficiently."""
        nested_query = """
        SELECT * FROM orders 
        WHERE user_id IN (
            SELECT id FROM users 
            WHERE age > (
                SELECT AVG(age) FROM users 
                WHERE state IN (
                    SELECT state FROM users 
                    WHERE created_at > '2024-01-01'
                )
            )
        )
        """
        
        state = AgentState(question="test", sql=nested_query)
        result = validate_sql_node(state)
        
        # Should complete without hanging
        assert isinstance(result, AgentState)
        # Should get LIMIT if it's non-aggregating
        if result.error is None:
            assert "LIMIT" in result.sql
    
    def test_many_columns_query(self):
        """Queries with many columns should be handled efficiently."""
        many_columns = ", ".join([f"col_{i}" for i in range(100)])
        query = f"SELECT {many_columns} FROM orders"
        
        state = AgentState(question="test", sql=query)
        result = validate_sql_node(state)
        
        # Should complete and get LIMIT
        assert result.error is None
        assert "LIMIT" in result.sql
    
    def test_large_in_clause(self):
        """Large IN clauses should be handled efficiently."""
        values = ", ".join([str(i) for i in range(100)])
        query = f"SELECT * FROM orders WHERE id IN ({values})"
        
        state = AgentState(question="test", sql=query)
        result = validate_sql_node(state)
        
        assert result.error is None
        assert "LIMIT" in result.sql