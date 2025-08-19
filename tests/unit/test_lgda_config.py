"""Unit tests for LGDA Configuration Management (LGDA-005)."""

import os
import warnings
from unittest.mock import patch

import pytest

from src.config import (
    ENVIRONMENT_PROFILES,
    ConfigFactory,
    CredentialManager,
    FeatureFlag,
    FeatureFlagManager,
    LGDAConfig,
    PerformanceConfig,
)


class TestLGDAConfig:
    """Test LGDA configuration with Pydantic BaseSettings."""

    def test_config_default_values(self):
        """Test that LGDA config has appropriate default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = LGDAConfig()

            assert config.environment == "development"
            assert config.debug is False
            assert config.log_level == "INFO"
            assert config.bigquery_project_id == ""
            assert config.bigquery_dataset == "bigquery-public-data.thelook_ecommerce"
            assert config.bigquery_location == "US"
            assert config.sql_max_limit == 1000
            assert config.allowed_tables == [
                "orders",
                "order_items",
                "products",
                "users",
            ]

    def test_config_environment_override(self):
        """Test that LGDA_* environment variables override defaults."""
        test_env = {
            "LGDA_ENVIRONMENT": "production",
            "LGDA_DEBUG": "true",
            "LGDA_LOG_LEVEL": "ERROR",
            "LGDA_BIGQUERY_PROJECT_ID": "test-project",
            "LGDA_BIGQUERY_LOCATION": "EU",
            "LGDA_SQL_MAX_LIMIT": "2000",
            "LGDA_GEMINI_API_KEY": "test-api-key",
            "LGDA_BEDROCK_REGION": "us-west-2",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = LGDAConfig()

            assert config.environment == "production"
            assert config.debug is True
            assert config.log_level == "ERROR"
            assert config.bigquery_project_id == "test-project"
            assert config.bigquery_location == "EU"
            assert config.sql_max_limit == 2000
            assert config.gemini_api_key == "test-api-key"
            assert config.bedrock_region == "us-west-2"

    def test_config_legacy_environment_variables(self):
        """Test that legacy environment variables work with warnings."""
        test_env = {
            "GOOGLE_API_KEY": "legacy-key",
            "BIGQUERY_PROJECT": "legacy-project",
            "DATASET_ID": "legacy-dataset",
            "MAX_BYTES_BILLED": "999999",
        }

        with patch.dict(os.environ, test_env, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                config = LGDAConfig()

                # Check that values are mapped correctly
                assert config.gemini_api_key == "legacy-key"
                assert config.bigquery_project_id == "legacy-project"
                assert config.bigquery_dataset == "legacy-dataset"
                assert config.sql_max_limit == 999999

                # Check that deprecation warnings were issued
                assert len(w) >= 4
                warning_messages = [str(warning.message) for warning in w]
                assert any("GOOGLE_API_KEY" in msg for msg in warning_messages)
                assert any("BIGQUERY_PROJECT" in msg for msg in warning_messages)

    def test_config_validation_environment(self):
        """Test environment field validation."""
        with patch.dict(os.environ, {"LGDA_ENVIRONMENT": "invalid"}, clear=True):
            with pytest.raises(ValueError, match="environment must be one of"):
                LGDAConfig()

    def test_config_validation_log_level(self):
        """Test log level field validation."""
        with patch.dict(os.environ, {"LGDA_LOG_LEVEL": "INVALID"}, clear=True):
            with pytest.raises(ValueError, match="log_level must be one of"):
                LGDAConfig()

    def test_config_lgda_prefix_priority(self):
        """Test that LGDA_* variables take priority over legacy ones."""
        test_env = {
            "GOOGLE_API_KEY": "legacy-key",
            "LGDA_GEMINI_API_KEY": "new-key",
            "BIGQUERY_PROJECT": "legacy-project",
            "LGDA_BIGQUERY_PROJECT_ID": "new-project",
        }

        with patch.dict(os.environ, test_env, clear=True):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # Ignore warnings for this test
                config = LGDAConfig()

                # LGDA_* variables should take priority
                assert config.gemini_api_key == "new-key"
                assert config.bigquery_project_id == "new-project"


class TestCredentialManager:
    """Test credential management functionality."""

    def test_credential_manager_initialization(self):
        """Test credential manager can be initialized."""
        config = LGDAConfig()
        cred_manager = CredentialManager(config)
        assert cred_manager.config == config
        assert cred_manager.secrets_cache == {}

    def test_bigquery_credentials_from_env(self):
        """Test BigQuery credentials from environment variable."""
        import base64
        import json

        test_creds = {"type": "service_account", "project_id": "test"}
        encoded_creds = base64.b64encode(json.dumps(test_creds).encode()).decode()

        with patch.dict(os.environ, {"LGDA_BIGQUERY_CREDENTIALS_JSON": encoded_creds}):
            config = LGDAConfig()
            cred_manager = CredentialManager(config)
            result = cred_manager.get_bigquery_credentials()

            assert isinstance(result, dict)
            assert result["type"] == "service_account"
            assert result["project_id"] == "test"

    def test_bigquery_credentials_from_file_path(self):
        """Test BigQuery credentials from file path."""
        test_path = "/path/to/credentials.json"
        with patch.dict(os.environ, {"LGDA_BIGQUERY_CREDENTIALS": test_path}):
            config = LGDAConfig()
            cred_manager = CredentialManager(config)
            result = cred_manager.get_bigquery_credentials()

            assert isinstance(result, str)
            assert test_path in result

    def test_bigquery_credentials_default(self):
        """Test BigQuery credentials default to ADC."""
        with patch.dict(os.environ, {}, clear=True):
            config = LGDAConfig()
            cred_manager = CredentialManager(config)
            result = cred_manager.get_bigquery_credentials()

            assert result is None  # Use Application Default Credentials

    def test_gemini_credentials(self):
        """Test Gemini credentials retrieval."""
        test_env = {
            "LGDA_GEMINI_API_KEY": "test-api-key",
            "LGDA_GEMINI_PROJECT_ID": "test-project",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = LGDAConfig()
            cred_manager = CredentialManager(config)
            result = cred_manager.get_gemini_credentials()

            assert result["api_key"] == "test-api-key"
            assert result["project_id"] == "test-project"

    def test_bedrock_credentials(self):
        """Test Bedrock credentials retrieval."""
        test_env = {
            "LGDA_BEDROCK_REGION": "us-west-2",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
        }

        with patch.dict(os.environ, test_env, clear=True):
            config = LGDAConfig()
            cred_manager = CredentialManager(config)
            result = cred_manager.get_bedrock_credentials()

            assert result["region"] == "us-west-2"
            assert result["aws_access_key_id"] == "test-access-key"
            assert result["aws_secret_access_key"] == "test-secret-key"

    def test_sensitive_data_masking(self):
        """Test that sensitive data is masked for logging."""
        config = LGDAConfig()
        cred_manager = CredentialManager(config)

        test_data = {
            "api_key": "secret123",
            "password": "super_secret",
            "token": "jwt_token",
            "normal_field": "public_data",
            "credentials": "cred_data",
        }

        masked = cred_manager.mask_sensitive_data(test_data)

        assert masked["api_key"] == "***MASKED***"
        assert masked["password"] == "***MASKED***"
        assert masked["token"] == "***MASKED***"
        assert masked["credentials"] == "***MASKED***"
        assert masked["normal_field"] == "public_data"


class TestFeatureFlags:
    """Test feature flag functionality."""

    def test_feature_flag_enum(self):
        """Test feature flag enum values."""
        assert FeatureFlag.ENABLE_QUERY_CACHE.value == "enable_query_cache"
        assert FeatureFlag.ENABLE_COST_TRACKING.value == "enable_cost_tracking"
        assert FeatureFlag.ENABLE_FALLBACK_LLM.value == "enable_fallback_llm"

    def test_feature_flag_manager_initialization(self):
        """Test feature flag manager initialization."""
        config = LGDAConfig()
        profile = ENVIRONMENT_PROFILES["development"]
        flag_manager = FeatureFlagManager(config, profile)

        assert flag_manager.config == config
        assert flag_manager.profile == profile
        assert flag_manager.custom_rules == {}

    def test_feature_flag_evaluation_development(self):
        """Test feature flag evaluation in development environment."""
        config = LGDAConfig()
        profile = ENVIRONMENT_PROFILES["development"]
        flag_manager = FeatureFlagManager(config, profile)

        # Development profile should have query cache disabled
        assert not flag_manager.is_enabled(FeatureFlag.ENABLE_QUERY_CACHE)
        assert not flag_manager.is_enabled(FeatureFlag.ENABLE_COST_TRACKING)

    def test_feature_flag_evaluation_production(self):
        """Test feature flag evaluation in production environment."""
        with patch.dict(os.environ, {"LGDA_ENVIRONMENT": "production"}, clear=True):
            config = LGDAConfig()
            profile = ENVIRONMENT_PROFILES["production"]
            flag_manager = FeatureFlagManager(config, profile)

            # Production profile should have most features enabled
            assert flag_manager.is_enabled(FeatureFlag.ENABLE_QUERY_CACHE)
            assert flag_manager.is_enabled(FeatureFlag.ENABLE_COST_TRACKING)
            assert flag_manager.is_enabled(FeatureFlag.ENABLE_FALLBACK_LLM)

    def test_custom_feature_flag_rules(self):
        """Test custom feature flag rules override profile settings."""
        config = LGDAConfig()
        profile = ENVIRONMENT_PROFILES["development"]
        flag_manager = FeatureFlagManager(config, profile)

        # Add custom rule that always returns True
        flag_manager.add_custom_rule(FeatureFlag.ENABLE_QUERY_CACHE, lambda ctx: True)

        # Should return True despite development profile having it disabled
        assert flag_manager.is_enabled(FeatureFlag.ENABLE_QUERY_CACHE)


class TestPerformanceConfig:
    """Test performance configuration."""

    def test_performance_config_defaults(self):
        """Test performance config default values."""
        perf_config = PerformanceConfig()

        assert perf_config.query_timeout == 300
        assert perf_config.max_concurrent_queries == 5
        assert perf_config.llm_timeout == 30
        assert perf_config.max_dataframe_rows == 10000

    def test_performance_config_for_development(self):
        """Test performance config for development environment."""
        perf_config = PerformanceConfig.for_environment("development")

        assert perf_config.query_timeout == 60
        assert perf_config.max_concurrent_queries == 2
        assert perf_config.max_dataframe_rows == 1000
        assert perf_config.max_memory_mb == 256

    def test_performance_config_for_production(self):
        """Test performance config for production environment."""
        perf_config = PerformanceConfig.for_environment("production")

        assert perf_config.query_timeout == 300
        assert perf_config.max_concurrent_queries == 10
        assert perf_config.max_dataframe_rows == 50000
        assert perf_config.max_memory_mb == 1024


class TestConfigFactory:
    """Test configuration factory."""

    def test_config_factory_create_config(self):
        """Test config factory creates proper configuration."""
        with patch.dict(os.environ, {"LGDA_ENVIRONMENT": "staging"}, clear=True):
            config = ConfigFactory.create_config()

            assert isinstance(config, LGDAConfig)
            assert config.environment == "staging"
            # Should apply staging profile overrides
            assert config.log_level == "INFO"
            assert config.sql_max_limit == 500

    def test_config_factory_create_managers(self):
        """Test config factory creates all managers."""
        config = LGDAConfig()
        cred_manager, feature_manager, perf_config = ConfigFactory.create_managers(
            config
        )

        assert isinstance(cred_manager, CredentialManager)
        assert isinstance(feature_manager, FeatureFlagManager)
        assert isinstance(perf_config, PerformanceConfig)

    def test_environment_profiles_exist(self):
        """Test that all required environment profiles exist."""
        assert "development" in ENVIRONMENT_PROFILES
        assert "staging" in ENVIRONMENT_PROFILES
        assert "production" in ENVIRONMENT_PROFILES

        for env_name, profile in ENVIRONMENT_PROFILES.items():
            assert profile.name == env_name
            assert isinstance(profile.config_overrides, dict)
            assert isinstance(profile.feature_flags, dict)
            assert isinstance(profile.performance_settings, dict)


class TestConfigIntegration:
    """Test configuration integration scenarios."""

    def test_full_configuration_workflow(self):
        """Test complete configuration workflow."""
        test_env = {
            "LGDA_ENVIRONMENT": "staging",
            "LGDA_DEBUG": "false",
            "LGDA_GEMINI_API_KEY": "test-key",
            "LGDA_SQL_MAX_LIMIT": "1500",
        }

        with patch.dict(os.environ, test_env, clear=True):
            # Create configuration
            config = ConfigFactory.create_config()
            assert config.environment == "staging"
            assert config.gemini_api_key == "test-key"

            # Create managers
            cred_manager, feature_manager, perf_config = ConfigFactory.create_managers(
                config
            )

            # Test credential management
            gemini_creds = cred_manager.get_gemini_credentials()
            assert gemini_creds["api_key"] == "test-key"

            # Test feature flags
            assert feature_manager.is_enabled(FeatureFlag.ENABLE_QUERY_CACHE)

            # Test performance config - uses staging environment
            perf_config_staging = PerformanceConfig.for_environment("staging")
            assert perf_config_staging.query_timeout == 300  # Uses default for staging

    def test_configuration_validation_error_handling(self):
        """Test configuration validation and error handling."""
        # Test invalid environment
        with patch.dict(os.environ, {"LGDA_ENVIRONMENT": "invalid"}, clear=True):
            with pytest.raises(ValueError):
                LGDAConfig()

        # Test invalid log level
        with patch.dict(os.environ, {"LGDA_LOG_LEVEL": "INVALID"}, clear=True):
            with pytest.raises(ValueError):
                LGDAConfig()

    def test_legacy_migration_warnings(self):
        """Test that legacy environment variables produce appropriate warnings."""
        test_env = {
            "GOOGLE_API_KEY": "legacy-key",
            "BIGQUERY_PROJECT": "legacy-project",
            "MAX_BYTES_BILLED": "999999",
        }

        with patch.dict(os.environ, test_env, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                config = LGDAConfig()

                # Should have deprecation warnings
                deprecation_warnings = [
                    warning
                    for warning in w
                    if issubclass(warning.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) > 0

                # Check warning messages mention migration
                messages = [str(warning.message) for warning in deprecation_warnings]
                assert any("migrate to LGDA_" in msg for msg in messages)
