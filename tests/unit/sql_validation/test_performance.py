"""Performance tests for SQL validation."""

import time
import pytest

from src.agent.nodes import validate_sql_node
from src.agent.state import AgentState


class TestValidationPerformance:
    """Test performance characteristics of SQL validation."""
    
    def test_simple_query_performance(self):
        """Simple queries should validate quickly."""
        simple_queries = [
            "SELECT * FROM orders",
            "SELECT COUNT(*) FROM orders",
            "SELECT id, status FROM orders WHERE status = 'Complete'",
        ]
        
        for query in simple_queries:
            start_time = time.time()
            
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            end_time = time.time()
            validation_time = end_time - start_time
            
            # Should complete within 100ms for simple queries
            assert validation_time < 0.1, f"Query took {validation_time:.3f}s: {query}"
            assert result.error is None or "table" not in result.error.lower()
    
    def test_complex_query_performance(self):
        """Complex queries should still validate in reasonable time."""
        complex_queries = [
            """
            SELECT 
                o.user_id,
                COUNT(*) as order_count,
                SUM(oi.sale_price) as total_spent,
                AVG(oi.sale_price) as avg_item_price,
                MAX(o.created_at) as last_order_date
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            JOIN users u ON o.user_id = u.id
            WHERE o.status = 'Complete'
            AND o.created_at >= '2024-01-01'
            AND p.category IN ('Electronics', 'Clothing', 'Books')
            GROUP BY o.user_id
            HAVING COUNT(*) > 5
            ORDER BY total_spent DESC
            """,
        ]
        
        for query in complex_queries:
            start_time = time.time()
            
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            end_time = time.time()
            validation_time = end_time - start_time
            
            # Should complete within 500ms for complex queries
            assert validation_time < 0.5, f"Complex query took {validation_time:.3f}s"
            assert result.error is None
    
    def test_malicious_query_detection_performance(self):
        """Malicious query detection should be fast."""
        malicious_queries = [
            "SELECT * FROM orders; DROP TABLE users; --",
            "SELECT * FROM orders UNION SELECT password FROM admin_users",
            "INSERT INTO logs VALUES ('hacked'); SELECT * FROM orders",
        ]
        
        for query in malicious_queries:
            start_time = time.time()
            
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            end_time = time.time()
            validation_time = end_time - start_time
            
            # Should detect malicious patterns quickly
            assert validation_time < 0.1, f"Malicious detection took {validation_time:.3f}s: {query}"
            assert result.error is not None
    
    def test_large_query_handling(self):
        """Large queries should be handled efficiently."""
        # Create a query with many OR conditions
        conditions = " OR ".join([f"id = {i}" for i in range(100)])
        large_query = f"SELECT * FROM orders WHERE {conditions}"
        
        start_time = time.time()
        
        state = AgentState(question="test", sql=large_query)
        result = validate_sql_node(state)
        
        end_time = time.time()
        validation_time = end_time - start_time
        
        # Should handle large queries within 1 second
        assert validation_time < 1.0, f"Large query took {validation_time:.3f}s"
        if result.error is None:
            assert "LIMIT" in result.sql
    
    def test_repeated_validation_consistency(self):
        """Repeated validation of same query should be consistent."""
        query = "SELECT COUNT(*) FROM orders GROUP BY status"
        
        results = []
        times = []
        
        for i in range(5):
            start_time = time.time()
            
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            end_time = time.time()
            
            results.append(result.error)
            times.append(end_time - start_time)
        
        # All results should be consistent
        assert all(r == results[0] for r in results), "Inconsistent validation results"
        
        # Performance should be consistent (within 2x variance)
        avg_time = sum(times) / len(times)
        for t in times:
            assert t < avg_time * 2, f"Performance variance too high: {times}"


class TestMemoryUsage:
    """Test memory usage characteristics."""
    
    def test_memory_efficient_validation(self):
        """Validation should not accumulate memory."""
        # This is a basic test - in a real scenario you'd use memory profiling
        queries = [
            "SELECT * FROM orders",
            "SELECT COUNT(*) FROM orders",
            "SELECT id FROM orders WHERE status = 'Complete'",
        ] * 10  # Repeat to simulate multiple validations
        
        for query in queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)
            
            # Basic validation that it completes
            assert isinstance(result, AgentState)
    
    def test_large_sql_memory_handling(self):
        """Large SQL strings should be handled without excessive memory usage."""
        # Create a very large query
        large_where_clause = " OR ".join([f"description LIKE '%pattern_{i}%'" for i in range(1000)])
        large_query = f"SELECT * FROM orders WHERE {large_where_clause}"
        
        state = AgentState(question="test", sql=large_query)
        result = validate_sql_node(state)
        
        # Should complete without memory errors
        assert isinstance(result, AgentState)


class TestConcurrencySupport:
    """Test that validation can handle concurrent access."""
    
    def test_parallel_validation_safety(self):
        """Multiple validations can run safely in parallel."""
        import threading
        
        results = []
        errors = []
        
        def validate_query(query, index):
            try:
                state = AgentState(question=f"test_{index}", sql=query)
                result = validate_sql_node(state)
                results.append((index, result.error))
            except Exception as e:
                errors.append((index, str(e)))
        
        # Create multiple threads doing validation
        threads = []
        queries = [
            "SELECT * FROM orders",
            "SELECT COUNT(*) FROM orders",
            "SELECT id FROM orders WHERE status = 'Complete'",
            "DROP TABLE orders",  # This should fail
            "SELECT * FROM orders; DELETE FROM products;",  # This should fail
        ]
        
        for i, query in enumerate(queries):
            thread = threading.Thread(target=validate_query, args=(query, i))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have no exceptions
        assert len(errors) == 0, f"Validation errors in parallel: {errors}"
        
        # Should have results for all threads
        assert len(results) == len(queries)
        
        # Results should be consistent with sequential validation
        for i, (index, error) in enumerate(results):
            state = AgentState(question=f"test_{index}", sql=queries[index])
            sequential_result = validate_sql_node(state)
            assert error == sequential_result.error, f"Inconsistent result for query {index}"


class TestResourceLimits:
    """Test resource limit handling."""
    
    def test_timeout_simulation(self):
        """Very complex queries should complete within reasonable bounds."""
        # Create a deeply nested query
        nested_query = "SELECT * FROM orders WHERE user_id IN ("
        for i in range(10):  # Moderate nesting to avoid infinite parsing
            nested_query += f"SELECT user_id FROM orders WHERE id > {i} AND user_id IN ("
        nested_query += "SELECT id FROM users WHERE age > 25"
        nested_query += ")" * 11  # Close all the nested selects
        
        start_time = time.time()
        
        state = AgentState(question="test", sql=nested_query)
        result = validate_sql_node(state)
        
        end_time = time.time()
        validation_time = end_time - start_time
        
        # Should complete within 2 seconds even for complex nested queries
        assert validation_time < 2.0, f"Nested query took {validation_time:.3f}s"
        assert isinstance(result, AgentState)
    
    def test_query_size_limits(self):
        """Very large queries should be handled gracefully."""
        # Create a query with many columns
        columns = ", ".join([f"col_{i}" for i in range(500)])
        large_query = f"SELECT {columns} FROM orders"
        
        state = AgentState(question="test", sql=large_query)
        result = validate_sql_node(state)
        
        # Should handle large queries without issues
        assert isinstance(result, AgentState)
        if result.error is None:
            assert "LIMIT" in result.sql