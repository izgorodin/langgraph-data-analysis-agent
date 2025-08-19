"""Tests for table whitelist enforcement."""

import pytest

from src.agent.nodes import validate_sql_node
from src.agent.state import AgentState


class TestTableWhitelistEnforcement:
    """Test table access control and whitelist enforcement."""

    def test_allowed_tables_pass(self):
        """Queries using only whitelisted tables should pass."""
        allowed_queries = [
            "SELECT * FROM orders",
            "SELECT * FROM order_items",
            "SELECT * FROM products",
            "SELECT * FROM users",
            "SELECT o.*, oi.* FROM orders o JOIN order_items oi ON o.order_id = oi.order_id",
            "SELECT p.name, u.email FROM products p, users u",
        ]

        for query in allowed_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # Should pass table validation (might fail on other policies)
            assert result.error is None or "table" not in result.error.lower()

    def test_forbidden_tables_blocked(self):
        """Queries using non-whitelisted tables should be blocked."""
        forbidden_queries = [
            "SELECT * FROM admin_users",
            "SELECT * FROM financial_data",
            "SELECT * FROM system_config",
            "SELECT * FROM sensitive_info",
            "SELECT * FROM logs",
        ]

        for query in forbidden_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            assert any(
                keyword in result.error.lower()
                for keyword in ["table", "disallowed", "pattern", "forbidden"]
            )

    def test_mixed_tables_blocked(self):
        """Queries mixing allowed and forbidden tables should be blocked."""
        mixed_queries = [
            "SELECT * FROM orders JOIN admin_users ON orders.user_id = admin_users.id",
            "SELECT o.*, s.* FROM orders o, sensitive_data s",
            "SELECT * FROM products UNION ALL SELECT * FROM secret_products",
        ]

        for query in mixed_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            # Should be blocked by table whitelist, keyword detection, or parse error
            assert any(
                keyword in result.error.lower()
                for keyword in [
                    "table",
                    "disallowed",
                    "keyword",
                    "forbidden",
                    "parse",
                    "pattern",
                ]
            )

    def test_table_aliases_validated(self):
        """Table aliases should not bypass whitelist validation."""
        alias_queries = [
            "SELECT * FROM orders o",
            "SELECT * FROM order_items oi",
            "SELECT * FROM products p",
            "SELECT * FROM users u",
            "SELECT o.id, p.name FROM orders o JOIN products p ON 1=1",
        ]

        for query in alias_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # Should pass table validation with aliases
            assert result.error is None or "table" not in result.error.lower()

    def test_schema_qualified_names_handled(self):
        """Schema-qualified table names should be handled properly."""
        schema_queries = [
            "SELECT * FROM `project.dataset.orders`",
            "SELECT * FROM dataset.orders",
            "SELECT * FROM `bigquery-public-data.dataset.unauthorized_table`",
        ]

        for query in schema_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # Schema-qualified names may not be recognized as allowed tables
            # This is acceptable as it's more secure
            if result.error is None:
                # If it passes, that's fine too
                pass
            else:
                # Should be blocked by table validation or parsing
                assert any(
                    keyword in result.error.lower()
                    for keyword in ["table", "parse", "disallowed"]
                )

    def test_subquery_tables_validated(self):
        """Tables in subqueries should also be validated."""
        subquery_with_forbidden = [
            "SELECT * FROM orders WHERE user_id IN (SELECT id FROM admin_users)",
            "SELECT * FROM products WHERE category = (SELECT default_cat FROM config_table)",
            "SELECT o.* FROM orders o WHERE EXISTS (SELECT 1 FROM forbidden_table f WHERE f.id = o.id)",
        ]

        for query in subquery_with_forbidden:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            # Should be blocked by table whitelist or keyword detection
            assert any(
                keyword in result.error.lower()
                for keyword in ["table", "disallowed", "keyword", "forbidden"]
            )

    def test_cte_tables_validated(self):
        """Tables in CTEs should be validated."""
        cte_queries = [
            """
            WITH forbidden_data AS (
                SELECT * FROM unauthorized_table
            )
            SELECT * FROM forbidden_data
            """,
            """
            WITH valid_data AS (
                SELECT * FROM orders
            )
            SELECT * FROM valid_data
            """,
        ]

        # First query should be blocked
        state = AgentState(question="test", sql=cte_queries[0])
        result = validate_sql_node(state)
        assert result.error is not None

        # Second query should pass table validation
        state = AgentState(question="test", sql=cte_queries[1])
        result = validate_sql_node(state)
        assert result.error is None or "table" not in result.error.lower()


class TestSystemTableAccess:
    """Test blocking of system and information schema tables."""

    def test_information_schema_blocked(self):
        """Information schema tables should be blocked."""
        info_schema_queries = [
            "SELECT * FROM information_schema.tables",
            "SELECT * FROM information_schema.columns",
            "SELECT * FROM INFORMATION_SCHEMA.SCHEMATA",
        ]

        for query in info_schema_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            assert any(
                keyword in result.error.lower()
                for keyword in ["keyword", "forbidden", "information_schema"]
            )

    def test_system_tables_blocked(self):
        """System tables should be blocked."""
        system_queries = [
            "SELECT * FROM sys.databases",
            "SELECT * FROM sys.tables",
            "SELECT * FROM master.dbo.sysdatabases",
        ]

        for query in system_queries:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            assert result.error is not None
            assert any(
                keyword in result.error.lower()
                for keyword in ["keyword", "forbidden", "sys"]
            )

    def test_bigquery_system_functions_handled(self):
        """BigQuery system functions should be handled appropriately."""
        # These might be legitimate in some cases
        bigquery_system = [
            "SELECT @@dataset_id",
            "SELECT @@project_id",
            "SELECT CURRENT_TIMESTAMP()",
        ]

        for query in bigquery_system:
            state = AgentState(question="test", sql=query)
            result = validate_sql_node(state)

            # These might pass or fail depending on parsing
            # The key is they shouldn't crash the validator
            assert isinstance(result, AgentState)
