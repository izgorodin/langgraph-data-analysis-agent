"""Tests for unified configuration management."""

import os
from unittest.mock import patch

from src.configuration.unified import (
    BigQueryConfig,
    LLMConfig,
    PerformanceConfig,
    SecurityConfig,
    UnifiedConfig,
    get_bigquery_config,
    get_llm_config,
    get_performance_config,
    get_security_config,
    get_unified_config,
)


class TestLLMConfig:
    """Test LLM configuration class."""

    def test_llm_config_defaults(self):
        """Test LLM configuration default values."""
        config = LLMConfig()

        assert config.max_tokens_planning == 800
        assert config.max_tokens_sql_generation == 1200
        assert config.max_tokens_analysis == 1000
        assert config.max_tokens_general == 4000

        assert config.temperature_planning == 0.1
        assert config.temperature_sql_generation == 0.0
        assert config.temperature_analysis == 0.2
        assert config.temperature_general == 0.0

        assert config.primary_provider == "gemini"
        assert config.fallback_provider == "bedrock"
        assert config.request_timeout == 30
        assert config.max_retries == 3

    def test_llm_config_environment_override(self):
        """Test that environment variables override LLM config defaults."""
        test_env = {
            "LGDA_LLM_MAX_TOKENS_PLANNING": "1000",
            "LGDA_LLM_MAX_TOKENS_SQL_GENERATION": "1500",
            "LGDA_LLM_PRIMARY_PROVIDER": "nvidia",
            "LGDA_LLM_REQUEST_TIMEOUT": "45",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = LLMConfig()

            assert config.max_tokens_planning == 1000
            assert config.max_tokens_sql_generation == 1500
            assert config.primary_provider == "nvidia"
            assert config.request_timeout == 45

    def test_get_max_tokens_for_context(self):
        """Test context-specific max tokens retrieval."""
        config = LLMConfig()

        assert config.get_max_tokens_for_context("planning") == 800
        assert config.get_max_tokens_for_context("sql_generation") == 1200
        assert config.get_max_tokens_for_context("analysis") == 1000
        assert config.get_max_tokens_for_context("general") == 4000
        assert config.get_max_tokens_for_context("unknown") == 4000  # fallback

    def test_get_temperature_for_context(self):
        """Test context-specific temperature retrieval."""
        config = LLMConfig()

        assert config.get_temperature_for_context("planning") == 0.1
        assert config.get_temperature_for_context("sql_generation") == 0.0
        assert config.get_temperature_for_context("analysis") == 0.2
        assert config.get_temperature_for_context("general") == 0.0
        assert config.get_temperature_for_context("unknown") == 0.0  # fallback


class TestBigQueryConfig:
    """Test BigQuery configuration class."""

    def test_bigquery_config_defaults(self):
        """Test BigQuery configuration default values."""
        config = BigQueryConfig()

        assert config.project_id == ""
        assert config.location == "US"
        assert config.dataset_id == "bigquery-public-data.thelook_ecommerce"
        assert config.max_bytes_billed == 100_000_000
        assert config.query_timeout == 300
        assert config.max_retries == 5

    def test_bigquery_config_environment_override(self):
        """Test that environment variables override defaults."""
        test_env = {
            "LGDA_BQ_PROJECT_ID": "test-project-123",
            "LGDA_BQ_LOCATION": "EU",
            "LGDA_BQ_MAX_BYTES_BILLED": "50000000",
            "LGDA_BQ_QUERY_TIMEOUT": "600",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = BigQueryConfig()

            assert config.project_id == "test-project-123"
            assert config.location == "EU"
            assert config.max_bytes_billed == 50_000_000
            assert config.query_timeout == 600


class TestSecurityConfig:
    """Test Security configuration class."""

    def test_security_config_defaults(self):
        """Test Security configuration default values."""
        config = SecurityConfig()

        assert config.max_sql_length == 10000
        assert config.allowed_tables == [
            "orders",
            "order_items",
            "products",
            "users",
        ]
        assert "DROP" in config.injection_patterns
        assert config.max_result_rows == 10000
        assert config.default_query_limit == 1000

    def test_security_config_environment_override(self):
        """Test that environment variables override defaults."""
        test_env = {
            "LGDA_SECURITY_MAX_SQL_LENGTH": "5000",
            "LGDA_SECURITY_DEFAULT_QUERY_LIMIT": "500",
            "LGDA_SECURITY_MAX_RESULT_ROWS": "20000",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = SecurityConfig()

            assert config.max_sql_length == 5000
            assert config.default_query_limit == 500
            assert config.max_result_rows == 20000


class TestPerformanceConfig:
    """Test Performance configuration class."""

    def test_performance_config_defaults(self):
        """Test Performance configuration default values."""
        config = PerformanceConfig()

        assert config.max_dataframe_rows == 10000
        assert config.max_memory_mb == 512
        assert config.enable_query_cache is True
        assert config.cache_ttl == 1800
        assert config.default_timeout == 30

    def test_performance_config_environment_override(self):
        """Test that environment variables override defaults."""
        test_env = {
            "LGDA_PERFORMANCE_MAX_DATAFRAME_ROWS": "50000",
            "LGDA_PERFORMANCE_ENABLE_QUERY_CACHE": "false",
            "LGDA_PERFORMANCE_DEFAULT_TIMEOUT": "60",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = PerformanceConfig()

            assert config.max_dataframe_rows == 50000
            assert config.enable_query_cache is False
            assert config.default_timeout == 60


class TestUnifiedConfig:
    """Test Unified configuration class."""

    def test_unified_config_defaults(self):
        """Test Unified configuration contains all components."""
        config = UnifiedConfig()

        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.bigquery, BigQueryConfig)
        assert isinstance(config.security, SecurityConfig)
        assert isinstance(config.performance, PerformanceConfig)

        assert config.environment == "development"
        assert config.debug is False
        assert config.log_level == "INFO"

    def test_unified_config_create_for_environment_development(self):
        """Test environment-specific configuration for development."""
        config = UnifiedConfig.create_for_environment("development")

        assert config.environment == "development"
        assert config.debug is True
        assert config.log_level == "DEBUG"
        assert config.security.default_query_limit == 100
        assert config.performance.max_dataframe_rows == 1000
        assert config.performance.enable_query_cache is False

    def test_unified_config_create_for_environment_production(self):
        """Test environment-specific configuration for production."""
        config = UnifiedConfig.create_for_environment("production")

        assert config.environment == "production"
        assert config.debug is False
        assert config.log_level == "WARNING"
        assert config.security.default_query_limit == 1000
        assert config.performance.max_dataframe_rows == 50000
        assert config.performance.enable_query_cache is True


class TestConfigurationAccessors:
    """Test configuration accessor functions."""

    def test_get_llm_config(self):
        """Test get_llm_config function."""
        config = get_llm_config()
        assert isinstance(config, LLMConfig)

    def test_get_bigquery_config(self):
        """Test get_bigquery_config function."""
        config = get_bigquery_config()
        assert isinstance(config, BigQueryConfig)

    def test_get_security_config(self):
        """Test get_security_config function."""
        config = get_security_config()
        assert isinstance(config, SecurityConfig)

    def test_get_performance_config(self):
        """Test get_performance_config function."""
        config = get_performance_config()
        assert isinstance(config, PerformanceConfig)

    def test_get_unified_config_cached(self):
        """Test that get_unified_config returns cached instance."""
        config1 = get_unified_config()
        config2 = get_unified_config()

        # Should be the same cached instance
        assert config1 is config2


class TestConfigurationConsolidation:
    """Test that configuration consolidation eliminates hardcoded values."""

    def test_llm_config_eliminates_hardcoded_max_tokens(self):
        """Test that LLM config provides context-specific max tokens."""
        config = LLMConfig()

        # Verify that we have different values for different contexts
        # This consolidates the scattered 800, 1000, 1200, 4000 values
        planning_tokens = config.get_max_tokens_for_context("planning")
        sql_tokens = config.get_max_tokens_for_context("sql_generation")
        analysis_tokens = config.get_max_tokens_for_context("analysis")
        general_tokens = config.get_max_tokens_for_context("general")

        assert planning_tokens == 800
        assert sql_tokens == 1200
        assert analysis_tokens == 1000
        assert general_tokens == 4000

        # All values should be configurable via environment
        with patch.dict(
            os.environ, {"LGDA_LLM_MAX_TOKENS_PLANNING": "2000"}, clear=True
        ):
            new_config = LLMConfig()
            assert new_config.get_max_tokens_for_context("planning") == 2000

    def test_bigquery_config_eliminates_hardcoded_timeouts(self):
        """Test that BigQuery config consolidates timeout values."""
        config = BigQueryConfig()

        # Default timeout should be configurable
        assert config.query_timeout == 300
        assert config.job_timeout == 300

        # Should be overridable via environment
        with patch.dict(os.environ, {"LGDA_BQ_QUERY_TIMEOUT": "600"}, clear=True):
            new_config = BigQueryConfig()
            assert new_config.query_timeout == 600

    def test_security_config_eliminates_hardcoded_allowed_tables(self):
        """Test that Security config consolidates allowed tables list."""
        config = SecurityConfig()

        # Default allowed tables should match existing behavior
        expected_tables = ["orders", "order_items", "products", "users"]
        assert config.allowed_tables == expected_tables

        # Should be configurable (though complex types need JSON in env vars)
        # This test verifies the default consolidates the hardcoded list
