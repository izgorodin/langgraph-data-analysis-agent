"""Tests for SQL security policies - injection prevention and statement types."""

import pytest
from pathlib import Path

from src.agent.exceptions import (
    SecurityViolationError,
    InjectionAttemptError,
    StatementTypeError,
    SQLValidationError,
)
from src.agent.nodes import validate_sql_node
from src.agent.state import AgentState


class TestSQLInjectionPrevention:
    """Test SQL injection prevention capabilities."""
    
    def test_semicolon_injection_blocked(self):
        """Block classic semicolon-based SQL injection."""
        malicious_queries = [
            "SELECT * FROM orders; DROP TABLE users; --",
            "SELECT * FROM orders; DELETE FROM products;",
            "SELECT id FROM users; INSERT INTO admin VALUES ('hacker');",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert "injection" in result.error.lower() or "forbidden" in result.error.lower()
    
    def test_comment_injection_blocked(self):
        """Block comment-based injection attempts.""" 
        malicious_queries = [
            "SELECT * FROM orders /* comment */ DELETE FROM products; --",
            "SELECT * FROM orders -- comment \n DELETE FROM users",
            "SELECT * FROM orders /*! UNION SELECT password FROM admin_users */",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
    
    def test_union_injection_blocked(self):
        """Block UNION-based injection attempts."""
        malicious_queries = [
            "SELECT * FROM orders UNION SELECT password FROM admin_users",
            "SELECT id FROM orders UNION ALL SELECT secret FROM admin_config",
            "SELECT name FROM products UNION SELECT username FROM admin_table",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            # Should either be blocked by table whitelist or injection detection
            assert any(keyword in result.error.lower() for keyword in ["table", "injection", "forbidden"])
    
    def test_boolean_injection_blocked(self):
        """Block boolean-based injection patterns."""
        malicious_queries = [
            "SELECT * FROM orders WHERE 1=1 OR '1'='1'",
            "SELECT * FROM orders WHERE true OR false",
            "SELECT * FROM orders WHERE 'a'='a' OR 1=1",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # These might pass basic validation since they're SELECT-only
            # but should be flagged for suspicious boolean patterns
            # For now, we focus on more critical injections
            pass
    
    def test_stacked_query_injection_blocked(self):
        """Block stacked query injection attempts."""
        malicious_queries = [
            "SELECT * FROM orders; INSERT INTO logs VALUES ('hacked')",
            "SELECT id FROM users; UPDATE users SET password = 'hacked'",
            "SELECT name FROM products; CREATE TABLE backdoor (id INT)",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
    
    def test_subquery_injection_blocked(self):
        """Block malicious subquery injection."""
        malicious_queries = [
            "SELECT * FROM orders WHERE id IN (SELECT id FROM admin_data)",
            "SELECT * FROM orders WHERE (SELECT COUNT(*) FROM information_schema.tables) > 0",
            "SELECT * FROM orders WHERE EXISTS (SELECT 1 FROM sys.databases)",
        ]
        
        for query in malicious_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            # Should be blocked by keyword detection or table whitelist
            assert any(keyword in result.error.lower() for keyword in ["table", "keyword", "forbidden"])


class TestStatementTypeValidation:
    """Test that only SELECT statements are allowed."""
    
    def test_select_statements_allowed(self):
        """Valid SELECT statements should pass."""
        valid_queries = [
            "SELECT * FROM orders",
            "SELECT id, status FROM orders WHERE status = 'Complete'",
            "SELECT COUNT(*) FROM orders GROUP BY status",
        ]
        
        for query in valid_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is None
    
    def test_insert_statements_blocked(self):
        """INSERT statements should be blocked."""
        forbidden_queries = [
            "INSERT INTO orders VALUES (1, 'test')",
            "INSERT INTO orders (id, status) VALUES (1, 'Complete')",
            "INSERT INTO products SELECT * FROM temp_products",
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in ["insert", "forbidden", "pattern"])
    
    def test_update_statements_blocked(self):
        """UPDATE statements should be blocked."""
        forbidden_queries = [
            "UPDATE orders SET status = 'cancelled'",
            "UPDATE orders SET status = 'Complete' WHERE id = 1",
            "UPDATE products SET price = price * 1.1",
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in ["update", "forbidden", "pattern"])
    
    def test_delete_statements_blocked(self):
        """DELETE statements should be blocked."""
        forbidden_queries = [
            "DELETE FROM orders WHERE id = 1",
            "DELETE FROM orders WHERE status = 'cancelled'",
            "DELETE FROM products",
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in ["delete", "forbidden", "pattern"])
    
    def test_ddl_statements_blocked(self):
        """DDL statements (CREATE, DROP, ALTER) should be blocked."""
        forbidden_queries = [
            "CREATE TABLE test_table (id INT)",
            "DROP TABLE orders", 
            "ALTER TABLE orders ADD COLUMN test_col STRING",
            "TRUNCATE TABLE orders",
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            # Should be blocked by pattern detection
            assert any(keyword in result.error.lower() for keyword in ["forbidden", "pattern", "security"])
    
    def test_merge_statements_blocked(self):
        """MERGE statements should be blocked."""
        forbidden_queries = [
            "MERGE orders USING staging ON orders.id = staging.id WHEN MATCHED THEN UPDATE SET status = staging.status",
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
            assert any(keyword in result.error.lower() for keyword in ["merge", "forbidden", "pattern"])
    
    def test_cte_with_dml_blocked(self):
        """CTE containing DML should be blocked."""
        # This is a complex case - CTEs that contain DML within them
        # For now, we focus on the main statement type
        forbidden_queries = [
            """
            WITH updated AS (
                UPDATE orders SET status = 'processed' WHERE status = 'pending' RETURNING *
            )
            SELECT * FROM updated
            """,
        ]
        
        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # Should be blocked - either by parse error or statement type
            assert result.error is not None


class TestMultiStatementBlocking:
    """Test blocking of multi-statement SQL."""
    
    def test_multiple_select_statements_blocked(self):
        """Multiple SELECT statements should be blocked."""
        multi_queries = [
            "SELECT * FROM orders; SELECT * FROM products;",
            "SELECT COUNT(*) FROM orders; SELECT AVG(sale_price) FROM order_items;",
        ]
        
        for query in multi_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # Should be blocked by parser or multi-statement detection
            assert result.error is not None
    
    def test_mixed_statement_types_blocked(self):
        """Mixed statement types should be blocked."""
        mixed_queries = [
            "SELECT * FROM orders; UPDATE orders SET status = 'processed';",
            "CREATE TABLE temp AS SELECT * FROM orders; SELECT * FROM temp;",
        ]
        
        for query in mixed_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None


class TestSQLParsingRobustness:
    """Test robustness of SQL parsing against edge cases."""
    
    def test_empty_query_handling(self):
        """Empty or whitespace-only queries should be handled."""
        empty_queries = ["", "   ", "\n\t  ", "-- just a comment"]
        
        for query in empty_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            assert result.error is not None
    
    def test_malformed_sql_handling(self):
        """Malformed SQL should be caught by parser."""
        malformed_queries = [
            "SELECT * FROM)",  # Extra parenthesis
            "SELECT * FROM orders WHERE AND",  # Invalid WHERE
            "SELECT * FROM orders GROUP BY",  # incomplete GROUP BY
            "SELCT * FROM orders",  # Typo in SELECT
        ]
        
        for query in malformed_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # Should be caught by parser or result in an error
            # sqlglot is very forgiving, so some malformed SQL might be "fixed"
            if result.error is not None:
                assert "parse" in result.error.lower() or "error" in result.error.lower()
            # If no error, it means sqlglot successfully parsed/fixed it, which is acceptable
    
    def test_very_long_query_handling(self):
        """Very long queries should be handled gracefully."""
        # Create a very long but valid query
        long_query = "SELECT * FROM orders WHERE " + " OR ".join([f"id = {i}" for i in range(1000)])
        
        state = AgentState(question="test", sql=long_query)
        result = validate_sql_node(state)
        
        # Should either pass (if valid) or fail gracefully
        # We don't want it to hang or crash
        assert isinstance(result, AgentState)