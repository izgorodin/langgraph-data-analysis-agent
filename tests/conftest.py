"""Test configuration and shared fixtures."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import google.generativeai as genai
import pandas as pd
import pytest
from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

# Test data directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir():
    """Path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    test_env = {
        "GOOGLE_API_KEY": "test-api-key",
        "BIGQUERY_PROJECT": "test-project",
        "BIGQUERY_LOCATION": "US",
        "DATASET_ID": "test-dataset.thelook_ecommerce",
        "ALLOWED_TABLES": "orders,order_items,products,users",
        "MAX_BYTES_BILLED": "100000000",
        "MODEL_NAME": "gemini-1.5-pro",
        "AWS_REGION": "us-east-1",
        "BEDROCK_MODEL_ID": "test-bedrock-model",
    }

    with patch.dict(os.environ, test_env, clear=True):
        yield test_env


@pytest.fixture
def sample_schema_response():
    """Sample BigQuery schema response for thelook_ecommerce tables."""
    return [
        {"table_name": "orders", "column_name": "order_id", "data_type": "INTEGER"},
        {"table_name": "orders", "column_name": "user_id", "data_type": "INTEGER"},
        {"table_name": "orders", "column_name": "status", "data_type": "STRING"},
        {"table_name": "orders", "column_name": "created_at", "data_type": "TIMESTAMP"},
        {
            "table_name": "orders",
            "column_name": "returned_at",
            "data_type": "TIMESTAMP",
        },
        {"table_name": "orders", "column_name": "shipped_at", "data_type": "TIMESTAMP"},
        {
            "table_name": "orders",
            "column_name": "delivered_at",
            "data_type": "TIMESTAMP",
        },
        {"table_name": "orders", "column_name": "num_of_item", "data_type": "INTEGER"},
        {"table_name": "order_items", "column_name": "id", "data_type": "INTEGER"},
        {
            "table_name": "order_items",
            "column_name": "order_id",
            "data_type": "INTEGER",
        },
        {"table_name": "order_items", "column_name": "user_id", "data_type": "INTEGER"},
        {
            "table_name": "order_items",
            "column_name": "product_id",
            "data_type": "INTEGER",
        },
        {
            "table_name": "order_items",
            "column_name": "inventory_item_id",
            "data_type": "INTEGER",
        },
        {"table_name": "order_items", "column_name": "status", "data_type": "STRING"},
        {
            "table_name": "order_items",
            "column_name": "created_at",
            "data_type": "TIMESTAMP",
        },
        {
            "table_name": "order_items",
            "column_name": "shipped_at",
            "data_type": "TIMESTAMP",
        },
        {
            "table_name": "order_items",
            "column_name": "delivered_at",
            "data_type": "TIMESTAMP",
        },
        {
            "table_name": "order_items",
            "column_name": "returned_at",
            "data_type": "TIMESTAMP",
        },
        {
            "table_name": "order_items",
            "column_name": "sale_price",
            "data_type": "FLOAT",
        },
        {"table_name": "products", "column_name": "id", "data_type": "INTEGER"},
        {"table_name": "products", "column_name": "cost", "data_type": "FLOAT"},
        {"table_name": "products", "column_name": "category", "data_type": "STRING"},
        {"table_name": "products", "column_name": "name", "data_type": "STRING"},
        {"table_name": "products", "column_name": "brand", "data_type": "STRING"},
        {"table_name": "products", "column_name": "retail_price", "data_type": "FLOAT"},
        {"table_name": "products", "column_name": "department", "data_type": "STRING"},
        {"table_name": "products", "column_name": "sku", "data_type": "STRING"},
        {
            "table_name": "products",
            "column_name": "distribution_center_id",
            "data_type": "INTEGER",
        },
        {"table_name": "users", "column_name": "id", "data_type": "INTEGER"},
        {"table_name": "users", "column_name": "first_name", "data_type": "STRING"},
        {"table_name": "users", "column_name": "last_name", "data_type": "STRING"},
        {"table_name": "users", "column_name": "email", "data_type": "STRING"},
        {"table_name": "users", "column_name": "age", "data_type": "INTEGER"},
        {"table_name": "users", "column_name": "gender", "data_type": "STRING"},
        {"table_name": "users", "column_name": "state", "data_type": "STRING"},
        {"table_name": "users", "column_name": "street_address", "data_type": "STRING"},
        {"table_name": "users", "column_name": "postal_code", "data_type": "STRING"},
        {"table_name": "users", "column_name": "city", "data_type": "STRING"},
        {"table_name": "users", "column_name": "country", "data_type": "STRING"},
        {"table_name": "users", "column_name": "latitude", "data_type": "FLOAT"},
        {"table_name": "users", "column_name": "longitude", "data_type": "FLOAT"},
        {"table_name": "users", "column_name": "traffic_source", "data_type": "STRING"},
        {"table_name": "users", "column_name": "created_at", "data_type": "TIMESTAMP"},
    ]


@pytest.fixture
def sample_query_result():
    """Sample query result DataFrame."""
    return pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4, 5],
            "user_id": [100, 101, 102, 103, 104],
            "status": ["Complete", "Processing", "Complete", "Cancelled", "Complete"],
            "total_amount": [45.99, 89.50, 123.75, 67.25, 156.00],
            "created_at": pd.to_datetime(
                [
                    "2024-01-01 10:00:00",
                    "2024-01-02 14:30:00",
                    "2024-01-03 09:15:00",
                    "2024-01-04 16:45:00",
                    "2024-01-05 11:20:00",
                ]
            ),
        }
    )


@pytest.fixture
def mock_bigquery_client(sample_schema_response, sample_query_result):
    """Mock BigQuery client with realistic responses."""
    with patch("src.bq.bigquery.Client") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock query job for schema queries
        mock_schema_job = Mock()
        mock_schema_job.result.return_value = sample_schema_response

        # Mock query job for data queries
        mock_data_job = Mock()
        mock_data_job.result.return_value.to_dataframe.return_value = (
            sample_query_result
        )

        # Setup query method as a Mock (not a function) for flexibility
        mock_client.query = Mock()

        # Default behavior: return appropriate job based on SQL content
        def default_query_side_effect(sql, job_config=None):
            if "INFORMATION_SCHEMA" in sql:
                return mock_schema_job
            else:
                return mock_data_job

        mock_client.query.side_effect = default_query_side_effect

        yield mock_client


@pytest.fixture
def sample_llm_responses():
    """Sample LLM responses for different prompt types."""
    return {
        "plan": '{"task": "sales_analysis", "tables": ["orders", "order_items"], "metrics": ["revenue", "count"], "filters": ["status = Complete"]}',
        "sql": "SELECT o.status, COUNT(*) as order_count, SUM(oi.sale_price) as revenue FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'Complete' GROUP BY o.status LIMIT 1000",
        "report": "Based on the analysis of 5 orders, the completed orders generate $482.49 in revenue with an average order value of $96.50. Key insights: 60% completion rate suggests room for improvement in order fulfillment. Next questions: 1) What factors contribute to order cancellations? 2) How does revenue vary by customer segment?",
    }


@pytest.fixture
def mock_gemini_client(sample_llm_responses):
    """Mock Gemini client with predictable responses."""
    with patch("src.llm.providers.gemini.genai") as mock_genai:
        mock_model = Mock()
        mock_response = Mock()

        def mock_generate_content(prompt):
            # Determine response type based on prompt content
            # If test explicitly set a return_value, respect it
            gen_mock = mock_model.generate_content
            try:
                forced = getattr(gen_mock, "return_value", None)
                # Only respect forced return if it looks explicitly set (has a 'text' attribute)
                if forced is not None and hasattr(forced, "text"):
                    return forced
            except Exception:
                pass
            # Prefer SQL classification if prompt includes SQL keywords
            if "sql" in prompt.lower() or "select" in prompt.lower():
                mock_response.text = sample_llm_responses["sql"]
            elif "plan" in prompt.lower() or "schema" in prompt.lower():
                mock_response.text = sample_llm_responses["plan"]
            else:
                mock_response.text = sample_llm_responses["report"]
            return mock_response

        # Use a Mock for generate_content so tests can assert call counts
        mock_model.generate_content = Mock(side_effect=mock_generate_content)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = Mock()

        yield mock_genai


# Ensure mock_gemini_client is available in test_llm_client module even if not requested
@pytest.fixture(autouse=True)
def _expose_mock_gemini_in_llm_tests(request, mock_gemini_client):
    import sys

    module = request.node.module
    if module.__name__.endswith("test_llm_client"):
        setattr(sys.modules[module.__name__], "mock_gemini_client", mock_gemini_client)


@pytest.fixture
def mock_llm_manager(sample_llm_responses):
    """Mock LLM manager for backward compatibility tests."""
    from src.llm.models import LLMContext, LLMProvider, LLMResponse

    # Create a simple function that returns predictable responses
    def mock_completion(prompt, system=None, model=None):
        # Determine response type based on prompt content
        prompt_lower = prompt.lower()
        if "plan" in prompt_lower or "schema" in prompt_lower:
            return sample_llm_responses["plan"]
        elif "sql" in prompt_lower or "select" in prompt_lower:
            return sample_llm_responses["sql"]
        else:
            return sample_llm_responses["report"]

    # Patch the llm_completion function directly from src.llm module
    with patch("src.llm.llm_completion", side_effect=mock_completion):
        with patch("src.llm.llm_fallback", side_effect=mock_completion):
            yield mock_completion


@pytest.fixture
def sample_agent_state():
    """Sample AgentState for testing."""
    from src.agent.state import AgentState

    return AgentState(
        question="What are the top selling products?",
        plan_json={"task": "product_analysis", "tables": ["products", "order_items"]},
        sql="SELECT p.name, SUM(oi.sale_price) as revenue FROM products p JOIN order_items oi ON p.id = oi.product_id GROUP BY p.name ORDER BY revenue DESC LIMIT 10",
        df_summary={
            "rows": 10,
            "columns": ["name", "revenue"],
            "head": [
                {"name": "Product A", "revenue": 1500.0},
                {"name": "Product B", "revenue": 1200.0},
            ],
            "describe": {"revenue": {"mean": 850.0, "std": 300.0}},
        },
        report="Top selling products analysis shows Product A leading with $1500 revenue.",
        history=[{"analysis": "Product performance analyzed"}],
    )


@pytest.fixture
def reset_global_client():
    """Reset global BigQuery client for test isolation."""
    import src.bq

    original_client = getattr(src.bq, "_bq_client", None)
    src.bq._bq_client = None
    yield
    src.bq._bq_client = original_client


@pytest.fixture(autouse=True)
def isolate_tests(reset_global_client, mock_env_vars):
    """Automatically isolate each test from global state and environment."""
    pass


# Error fixtures for testing exception handling
@pytest.fixture
def mock_bigquery_error():
    """Mock BigQuery errors for testing error handling."""
    return BadRequest("Invalid query syntax")


@pytest.fixture
def mock_gemini_error():
    """Mock Gemini API errors for testing error handling."""
    error = Exception("API quota exceeded")
    return error
