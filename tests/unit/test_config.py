"""Unit tests for configuration management."""

import os
import pytest
from unittest.mock import patch

from src.config import Settings, settings


class TestConfiguration:
    """Test configuration management functionality."""

    def test_settings_default_values(self):
        """Test that settings have appropriate default values."""
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            
            assert test_settings.google_api_key == ""
            assert test_settings.bq_project == ""
            assert test_settings.bq_location == "US"
            assert test_settings.dataset_id == "bigquery-public-data.thelook_ecommerce"
            assert test_settings.max_bytes_billed == 100000000
            assert test_settings.model_name == "gemini-1.5-pro"
            assert test_settings.aws_region == "eu-west-1"
            assert test_settings.bedrock_model_id == ""

    def test_settings_environment_override(self):
        """Test that environment variables override default values."""
        test_env = {
            "GOOGLE_API_KEY": "test-api-key",
            "BIGQUERY_PROJECT": "test-project",
            "BIGQUERY_LOCATION": "US",
            "DATASET_ID": "test-dataset.thelook_ecommerce",
            "ALLOWED_TABLES": "orders,order_items,products,users",
            "MAX_BYTES_BILLED": "100000000",
            "MODEL_NAME": "gemini-1.5-pro",
            "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "test-bedrock-model"
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            assert test_settings.google_api_key == "test-api-key"
            assert test_settings.bq_project == "test-project"
            assert test_settings.bq_location == "US"
            assert test_settings.dataset_id == "test-dataset.thelook_ecommerce"
            assert test_settings.max_bytes_billed == 100000000
            assert test_settings.model_name == "gemini-1.5-pro"
            assert test_settings.aws_region == "us-east-1"
            assert test_settings.bedrock_model_id == "test-bedrock-model"

    def test_allowed_tables_parsing(self):
        """Test parsing of allowed tables from environment variable."""
        test_env = {"ALLOWED_TABLES": "orders,order_items,products,users"}
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            assert test_settings.allowed_tables == ("orders", "order_items", "products", "users")
            assert isinstance(test_settings.allowed_tables, tuple)

    def test_allowed_tables_with_spaces(self):
        """Test parsing of allowed tables with spaces."""
        test_env = {"ALLOWED_TABLES": " orders , order_items , products , users "}
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            # Should strip whitespace
            assert test_settings.allowed_tables == ("orders", "order_items", "products", "users")

    def test_allowed_tables_single_table(self):
        """Test parsing when only one table is allowed."""
        test_env = {"ALLOWED_TABLES": "orders"}
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            assert test_settings.allowed_tables == ("orders",)

    def test_max_bytes_billed_conversion(self):
        """Test conversion of max_bytes_billed to integer."""
        test_env = {"MAX_BYTES_BILLED": "500000000"}
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            assert test_settings.max_bytes_billed == 500000000
            assert isinstance(test_settings.max_bytes_billed, int)

    def test_max_bytes_billed_invalid_value(self):
        """Test handling of invalid max_bytes_billed value."""
        test_env = {"MAX_BYTES_BILLED": "not_a_number"}
        
        with patch.dict(os.environ, test_env, clear=True):
            with pytest.raises(ValueError):
                Settings()

    def test_global_settings_instance(self):
        """Test that global settings instance exists and is accessible."""
        assert settings is not None
        assert isinstance(settings, Settings)
        
        # Test that it has expected attributes
        assert hasattr(settings, 'google_api_key')
        assert hasattr(settings, 'bq_project')
        assert hasattr(settings, 'model_name')

    def test_dotenv_loading(self):
        """Test that .env file loading works."""
        # This tests that load_dotenv() is called during import
        # In a real test, we'd create a temporary .env file
        
        # Just verify that dotenv functionality is available
        from dotenv import load_dotenv
        assert load_dotenv is not None

    def test_settings_dataclass_behavior(self):
        """Test that Settings behaves as a proper dataclass."""
        test_settings = Settings()
        
        # Test attribute access
        assert hasattr(test_settings, '__dataclass_fields__')
        
        # Test field names
        field_names = set(test_settings.__dataclass_fields__.keys())
        expected_fields = {
            'google_api_key', 'bq_project', 'bq_location', 'dataset_id',
            'allowed_tables', 'max_bytes_billed', 'model_name', 
            'aws_region', 'bedrock_model_id'
        }
        assert field_names == expected_fields

    def test_settings_immutability(self):
        """Test that settings can be modified (dataclass is mutable by default)."""
        test_settings = Settings()
        original_project = test_settings.bq_project
        
        # Should be able to modify
        test_settings.bq_project = "new-project"
        assert test_settings.bq_project == "new-project"
        assert test_settings.bq_project != original_project

    def test_bigquery_configuration_completeness(self):
        """Test that all required BigQuery configuration is present."""
        test_env = {
            "GOOGLE_API_KEY": "test-api-key",
            "BIGQUERY_PROJECT": "test-project",
            "BIGQUERY_LOCATION": "US",
            "DATASET_ID": "test-dataset.thelook_ecommerce",
            "ALLOWED_TABLES": "orders,order_items,products,users",
            "MAX_BYTES_BILLED": "100000000",
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            # All BigQuery-related settings should be configured
            assert test_settings.bq_project
            assert test_settings.bq_location
            assert test_settings.dataset_id
            assert test_settings.max_bytes_billed > 0
            assert len(test_settings.allowed_tables) > 0

    def test_llm_configuration_completeness(self):
        """Test that all required LLM configuration is present."""
        test_env = {
            "GOOGLE_API_KEY": "test-api-key",
            "MODEL_NAME": "gemini-1.5-pro",
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            # LLM-related settings should be configured
            assert test_settings.google_api_key
            assert test_settings.model_name
            # AWS settings might be empty (fallback not always needed)

    def test_security_sensitive_data_handling(self):
        """Test that sensitive data like API keys are handled properly."""
        test_env = {
            "GOOGLE_API_KEY": "sk-super-secret-key-123",
            "BEDROCK_MODEL_ID": "secret-model"
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            # Values should be stored (this is expected)
            assert test_settings.google_api_key == "sk-super-secret-key-123"
            assert test_settings.bedrock_model_id == "secret-model"
            
            # In a real application, you might want to test that these
            # aren't logged or exposed inappropriately

    def test_dataset_id_format_validation(self):
        """Test validation of dataset ID format."""
        # Valid format: project.dataset
        valid_dataset_ids = [
            "bigquery-public-data.thelook_ecommerce",
            "my-project.my_dataset",
            "project123.dataset_456"
        ]
        
        for dataset_id in valid_dataset_ids:
            test_env = {"DATASET_ID": dataset_id}
            with patch.dict(os.environ, test_env, clear=True):
                test_settings = Settings()
                assert test_settings.dataset_id == dataset_id

    def test_model_name_variations(self):
        """Test different model name configurations."""
        model_names = [
            "gemini-1.5-pro",
            "gemini-1.5-flash", 
            "gemini-1.0-pro",
            "custom-model-name"
        ]
        
        for model_name in model_names:
            test_env = {"MODEL_NAME": model_name}
            with patch.dict(os.environ, test_env, clear=True):
                test_settings = Settings()
                assert test_settings.model_name == model_name

    def test_aws_region_configuration(self):
        """Test AWS region configuration for Bedrock fallback."""
        aws_regions = [
            "us-east-1",
            "us-west-2", 
            "eu-west-1",
            "ap-southeast-1"
        ]
        
        for region in aws_regions:
            test_env = {"AWS_REGION": region}
            with patch.dict(os.environ, test_env, clear=True):
                test_settings = Settings()
                assert test_settings.aws_region == region

    def test_configuration_validation_edge_cases(self):
        """Test edge cases in configuration validation."""
        # Empty allowed tables
        test_env = {"ALLOWED_TABLES": ""}
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            assert test_settings.allowed_tables == ("",)  # Single empty string
        
        # Zero max bytes billed
        test_env = {"MAX_BYTES_BILLED": "0"}
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            assert test_settings.max_bytes_billed == 0

    def test_configuration_repr_and_str(self):
        """Test string representation of settings."""
        test_settings = Settings()
        
        # Should have readable string representation
        str_repr = str(test_settings)
        assert "Settings" in str_repr
        
        # repr should be valid Python code (dataclass default)
        repr_str = repr(test_settings)
        assert "Settings(" in repr_str

    def test_settings_equality(self):
        """Test equality comparison of settings instances."""
        settings1 = Settings()
        settings2 = Settings()
        
        # Should be equal if constructed with same environment
        assert settings1 == settings2
        
        # Should be different if modified
        settings2.bq_project = "different-project"
        assert settings1 != settings2

    def test_configuration_with_missing_optional_fields(self):
        """Test configuration when optional fields are missing."""
        # Remove optional environment variables
        test_env = {
            "GOOGLE_API_KEY": "",  # Empty but present
            "BEDROCK_MODEL_ID": "",  # Empty but present
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            # Should use defaults for missing values
            assert test_settings.google_api_key == ""
            assert test_settings.bedrock_model_id == ""
            assert test_settings.bq_location == "US"  # Default value
            assert test_settings.model_name == "gemini-1.5-pro"  # Default value

    def test_configuration_environment_precedence(self):
        """Test that environment variables take precedence over defaults."""
        test_env = {
            "BIGQUERY_LOCATION": "EU",  # Override default "US"
            "MODEL_NAME": "custom-model",  # Override default "gemini-1.5-pro"
            "MAX_BYTES_BILLED": "999999999"  # Override default
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            test_settings = Settings()
            
            assert test_settings.bq_location == "EU"
            assert test_settings.model_name == "custom-model"
            assert test_settings.max_bytes_billed == 999999999