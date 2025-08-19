"""Unit tests for BigQuery client functionality."""

import os
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from google.api_core.exceptions import BadRequest, Forbidden, NotFound

from src.bq import bq_client, get_schema, run_query


class TestBigQueryClient:
    """Test BigQuery client functionality with complete mocking."""

    def test_bq_client_initialization(self, mock_bigquery_client):
        """Test BigQuery client initialization."""
        # Use environment variables
        test_env = {"BIGQUERY_PROJECT": "test-project", "BIGQUERY_LOCATION": "US"}

        with patch.dict(os.environ, test_env, clear=True):
            # Reset global state first
            import src.bq

            src.bq._bq_client = None

            with patch("src.bq.bigquery.Client") as mock_client_class:
                # Need to reload both config and bq modules to pick up new environment
                from importlib import reload

                import src.config

                reload(src.config)
                reload(src.bq)  # This will re-import settings with new values

                from src.bq import bq_client

                client = bq_client()

                # Verify client is created with correct parameters
                mock_client_class.assert_called_once_with(
                    project="test-project", location="US"
                )
                assert client is not None

    def test_bq_client_singleton_behavior(self, mock_bigquery_client, mock_env_vars):
        """Test that bq_client returns the same instance (singleton behavior)."""
        with patch("src.bq.bigquery.Client") as mock_client_class:
            client1 = bq_client()
            client2 = bq_client()

            # Should only create client once
            assert mock_client_class.call_count == 1
            assert client1 is client2

    def test_get_schema_success(self, mock_bigquery_client, sample_schema_response):
        """Test successful schema retrieval."""
        # Setup mock to return schema data for INFORMATION_SCHEMA query
        tables = ["orders", "order_items"]

        result = get_schema(tables)

        assert isinstance(result, list)
        assert len(result) > 0

        # Verify structure of schema response
        for row in result:
            assert "table_name" in row
            assert "column_name" in row
            assert "data_type" in row
            assert row["table_name"] in ["orders", "order_items", "products", "users"]

    def test_get_schema_with_query_parameters(self, mock_bigquery_client):
        """Test that get_schema passes correct query parameters."""
        with patch("src.bq.bigquery.QueryJobConfig") as mock_job_config:
            with patch("src.bq.bigquery.ArrayQueryParameter") as mock_array_param:
                tables = ["orders", "products"]

                get_schema(tables)

                # Verify ArrayQueryParameter is called correctly
                mock_array_param.assert_called_once_with("tables", "STRING", tables)

                # Verify QueryJobConfig includes the parameter
                mock_job_config.assert_called_once()
                call_args = mock_job_config.call_args
                assert "query_parameters" in call_args.kwargs
                assert "maximum_bytes_billed" in call_args.kwargs

    def test_run_query_success(self, mock_bigquery_client, sample_query_result):
        """Test successful query execution."""
        sql = "SELECT * FROM orders WHERE status = 'Complete' LIMIT 10"

        result = run_query(sql)

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert "order_id" in result.columns

    def test_run_query_dry_run(self, mock_bigquery_client):
        """Test dry run mode for query validation."""
        sql = "SELECT * FROM orders"

        with patch("src.bq.bigquery.QueryJobConfig") as mock_job_config:
            run_query(sql, dry_run=True)

            # Verify dry_run is set to True
            mock_job_config.assert_called_once()
            call_args = mock_job_config.call_args
            assert call_args.kwargs["dry_run"] is True

    def test_run_query_with_job_config(self, mock_bigquery_client):
        """Test that run_query creates proper job configuration."""
        sql = "SELECT COUNT(*) FROM orders"

        with patch("src.bq.bigquery.QueryJobConfig") as mock_job_config:
            run_query(sql)

            # Verify job config is created with correct parameters
            mock_job_config.assert_called_once()
            call_args = mock_job_config.call_args

            assert "maximum_bytes_billed" in call_args.kwargs
            assert "dry_run" in call_args.kwargs
            assert "use_query_cache" in call_args.kwargs
            assert call_args.kwargs["use_query_cache"] is True

    def test_run_query_bad_request_error(self, mock_bigquery_client):
        """Test handling of BigQuery BadRequest errors."""
        sql = "INVALID SQL SYNTAX"

        # Mock client to raise BadRequest
        mock_job = Mock()
        mock_job.result.side_effect = BadRequest("Invalid SQL syntax")

        # Clear the default side_effect and set return_value
        mock_bigquery_client.query.side_effect = None
        mock_bigquery_client.query.return_value = mock_job

        with pytest.raises(ValueError) as exc_info:
            run_query(sql)

        assert "BigQuery error:" in str(exc_info.value)
        assert "Invalid SQL syntax" in str(exc_info.value)

    def test_run_query_authentication_error(self, mock_bigquery_client):
        """Test handling of authentication errors."""
        sql = "SELECT * FROM orders"

        # Mock client to raise Forbidden (authentication error)
        mock_bigquery_client.query.side_effect = Forbidden("Authentication failed")

        with pytest.raises(Forbidden):
            run_query(sql)

    def test_run_query_not_found_error(self, mock_bigquery_client):
        """Test handling of table/dataset not found errors."""
        sql = "SELECT * FROM non_existent_table"

        # Mock client to raise NotFound
        mock_bigquery_client.query.side_effect = NotFound("Table not found")

        with pytest.raises(NotFound):
            run_query(sql)

    def test_schema_query_format(self, mock_env_vars):
        """Test that SCHEMA_QUERY is properly formatted."""
        from src.bq import SCHEMA_QUERY

        assert "INFORMATION_SCHEMA.COLUMNS" in SCHEMA_QUERY
        assert "@tables" in SCHEMA_QUERY
        assert "table_name" in SCHEMA_QUERY
        assert "column_name" in SCHEMA_QUERY
        assert "data_type" in SCHEMA_QUERY
        assert "ORDER BY" in SCHEMA_QUERY

    def test_get_schema_empty_tables(self, mock_bigquery_client):
        """Test get_schema with empty table list."""
        result = get_schema([])

        # Should still work but return empty or filtered results
        assert isinstance(result, list)

    def test_run_query_large_result_handling(self, mock_bigquery_client):
        """Test handling of large query results."""
        sql = "SELECT * FROM large_table"

        # Mock a large DataFrame
        large_df = pd.DataFrame(
            {"id": range(10000), "value": [f"value_{i}" for i in range(10000)]}
        )

        mock_job = Mock()
        mock_job.result.return_value.to_dataframe.return_value = large_df

        # Clear the default side_effect and set return_value
        mock_bigquery_client.query.side_effect = None
        mock_bigquery_client.query.return_value = mock_job

        result = run_query(sql)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 10000

    def test_bq_client_with_bqstorage(self, mock_bigquery_client):
        """Test that BigQuery Storage is used for large result sets."""
        sql = "SELECT * FROM orders"

        # Set up proper mock chain
        mock_job = Mock()
        mock_result = Mock()
        mock_job.result.return_value = mock_result

        # Clear the default side_effect and set return_value
        mock_bigquery_client.query.side_effect = None
        mock_bigquery_client.query.return_value = mock_job

        run_query(sql)

        # Verify to_dataframe is called with create_bqstorage_client=True
        mock_result.to_dataframe.assert_called_once_with(create_bqstorage_client=True)

    def test_concurrent_query_execution(self, mock_bigquery_client):
        """Test that multiple queries can be executed concurrently."""
        import threading
        import time

        results = []
        errors = []

        def execute_query(query_id):
            try:
                sql = f"SELECT {query_id} as id"
                result = run_query(sql)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=execute_query, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all queries succeeded
        assert len(errors) == 0
        assert len(results) == 3

    def test_query_timeout_handling(self, mock_bigquery_client):
        """Test handling of query timeouts."""
        sql = "SELECT * FROM very_large_table"

        # Mock timeout scenario
        mock_job = Mock()
        mock_job.result.side_effect = Exception("Query timeout")

        # Clear the default side_effect and set return_value
        mock_bigquery_client.query.side_effect = None
        mock_bigquery_client.query.return_value = mock_job

        with pytest.raises(Exception) as exc_info:
            run_query(sql)

        assert "timeout" in str(exc_info.value).lower()

    def test_global_client_reset(self, reset_global_client):
        """Test that global client can be reset between tests."""
        import src.bq

        # Verify client is None initially (due to reset_global_client fixture)
        assert src.bq._bq_client is None

        # Create client
        with patch("src.bq.bigquery.Client") as mock_client_class:
            client = bq_client()
            assert src.bq._bq_client is not None

        # After fixture cleanup, it should be reset again

    def test_schema_response_structure(self, sample_schema_response):
        """Test that schema response has expected structure."""
        # Verify sample schema response structure
        assert isinstance(sample_schema_response, list)

        for row in sample_schema_response:
            assert isinstance(row, dict)
            assert "table_name" in row
            assert "column_name" in row
            assert "data_type" in row

            # Verify data types are valid BigQuery types
            assert row["data_type"] in [
                "INTEGER",
                "STRING",
                "FLOAT",
                "TIMESTAMP",
                "BOOLEAN",
            ]

            # Verify table names are from allowed set
            assert row["table_name"] in ["orders", "order_items", "products", "users"]

    def test_error_message_formatting(self, mock_bigquery_client):
        """Test that error messages are properly formatted."""
        sql = "INVALID SQL"

        original_error = BadRequest("Syntax error at line 1")
        mock_job = Mock()
        mock_job.result.side_effect = original_error

        # Clear the default side_effect and set return_value
        mock_bigquery_client.query.side_effect = None
        mock_bigquery_client.query.return_value = mock_job

        with pytest.raises(ValueError) as exc_info:
            run_query(sql)

        error_message = str(exc_info.value)
        assert error_message.startswith("BigQuery error:")
        assert "Syntax error at line 1" in error_message
