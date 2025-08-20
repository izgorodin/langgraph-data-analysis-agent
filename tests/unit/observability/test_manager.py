"""Test suite for LGDA observability manager and configuration integration."""

import os
from unittest.mock import Mock, patch

import pytest

from src.config import LGDAConfig
from src.observability.manager import (
    ObservabilityManager,
    get_observability_manager,
    setup_observability,
    shutdown_observability,
)


class TestObservabilityManager:
    """Test cases for observability manager functionality."""

    def test_manager_initialization_default_config(self):
        """Test manager initialization with default configuration."""
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "false"}):
            manager = ObservabilityManager()
            assert manager.config is not None
            assert len(manager.components) == 5  # All components should be initialized

    def test_manager_initialization_custom_config(self):
        """Test manager initialization with custom configuration."""
        with patch.dict(
            os.environ,
            {
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_METRICS_ENABLED": "true",
                "LGDA_LOGGING_ENABLED": "false",
                "LGDA_TRACING_ENABLED": "true",
                "LGDA_HEALTH_MONITORING_ENABLED": "false",
                "LGDA_BUSINESS_METRICS_ENABLED": "true",
            },
        ):
            config = LGDAConfig()
            manager = ObservabilityManager(config)
            assert manager.config == config

            # Check effective configuration
            effective = config.effective_observability_config
            assert effective["metrics"] is True
            assert effective["logging"] is False  # Disabled
            assert effective["tracing"] is True
            assert effective["health_monitoring"] is False  # Disabled
            assert effective["business_metrics"] is True

    def test_manager_with_observability_disabled(self):
        """Test manager when observability is completely disabled."""
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            config = LGDAConfig()
            manager = ObservabilityManager(config)

            # All components should be disabled
            effective = config.effective_observability_config
            assert all(not enabled for enabled in effective.values())

            # But components should still exist (just disabled)
            assert len(manager.components) == 5

    def test_get_components(self):
        """Test getting individual components."""
        manager = ObservabilityManager()

        # Test all component getters
        metrics = manager.get_metrics()
        logger = manager.get_logger()
        tracer = manager.get_tracer()
        health = manager.get_health_monitor()
        business = manager.get_business_metrics()

        assert metrics is not None
        assert logger is not None
        assert tracer is not None
        assert health is not None
        assert business is not None

        # Test get_all_components
        all_components = manager.get_all_components()
        assert len(all_components) == 5
        assert "metrics" in all_components
        assert "logging" in all_components
        assert "tracing" in all_components
        assert "health" in all_components
        assert "business_metrics" in all_components

    def test_health_status_integration(self):
        """Test health status integration."""
        manager = ObservabilityManager()

        health_status = manager.get_health_status()
        assert isinstance(health_status, dict)
        assert "status" in health_status
        assert "timestamp" in health_status

    def test_metrics_summary_integration(self):
        """Test metrics summary integration."""
        manager = ObservabilityManager()

        summary = manager.get_metrics_summary(hours=1)
        assert isinstance(summary, dict)
        assert "enabled" in summary

    def test_configure_health_checks(self):
        """Test configuring health checks."""
        manager = ObservabilityManager()

        # Mock functions for health checks
        bq_client_func = Mock()
        llm_test_func = Mock()

        # Should not raise exceptions
        manager.configure_bigquery_health_check(bq_client_func)
        manager.configure_llm_health_check(llm_test_func)

    def test_cleanup_old_metrics(self):
        """Test cleaning up old metrics."""
        config = LGDAConfig(metrics_retention_hours=1)
        manager = ObservabilityManager(config)

        # Should not raise exception
        manager.cleanup_old_metrics()

    def test_is_enabled_property(self):
        """Test is_enabled property."""
        with patch.dict(os.environ, {"LGDA_OBSERVABILITY_ENABLED": "true"}):
            config_enabled = LGDAConfig()
            manager_enabled = ObservabilityManager(config_enabled)
            assert manager_enabled.is_enabled() is True

        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            config_disabled = LGDAConfig()
            manager_disabled = ObservabilityManager(config_disabled)
            assert manager_disabled.is_enabled() is False

    def test_shutdown(self):
        """Test manager shutdown."""
        manager = ObservabilityManager()

        # Should not raise exception
        manager.shutdown()


class TestGlobalObservabilityManager:
    """Test cases for global observability manager functions."""

    def test_get_observability_manager_singleton(self):
        """Test that get_observability_manager returns singleton."""
        manager1 = get_observability_manager()
        manager2 = get_observability_manager()

        assert manager1 is manager2

    def test_get_observability_manager_with_config(self):
        """Test get_observability_manager with custom config."""
        # Use valid environment value
        config = LGDAConfig()  # Use default config since "test" is not valid
        manager = get_observability_manager(config)

        assert manager.config.environment == "development"  # Uses default environment

    def test_setup_observability(self):
        """Test setup_observability convenience function."""
        config = LGDAConfig()  # Use default config
        manager = setup_observability(config)

        assert isinstance(manager, ObservabilityManager)
        assert manager.config.environment == "development"  # Default environment

    def test_shutdown_observability(self):
        """Test shutdown_observability function."""
        # First get a manager
        get_observability_manager()

        # Then shut it down
        shutdown_observability()

        # Should not raise exception

    def teardown_method(self):
        """Reset global manager after each test."""
        import src.observability.manager

        src.observability.manager._global_observability_manager = None


class TestConfigIntegration:
    """Test cases for configuration integration."""

    def test_config_observability_properties(self):
        """Test observability properties in LGDAConfig."""
        with patch.dict(
            os.environ,
            {
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_DISABLE_OBSERVABILITY": "false",
                "LGDA_METRICS_ENABLED": "true",
                "LGDA_LOGGING_ENABLED": "false",
            },
        ):
            config = LGDAConfig()

            assert config.is_observability_enabled is True

            effective = config.effective_observability_config
            assert effective["metrics"] is True
            assert effective["logging"] is False

    def test_config_disable_observability_flag(self):
        """Test that disable_observability flag overrides everything."""
        with patch.dict(
            os.environ,
            {
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_DISABLE_OBSERVABILITY": "true",  # This should override everything
                "LGDA_METRICS_ENABLED": "true",
                "LGDA_LOGGING_ENABLED": "true",
            },
        ):
            config = LGDAConfig()

            assert config.is_observability_enabled is False

            effective = config.effective_observability_config
            assert all(not enabled for enabled in effective.values())

    def test_config_environment_variables(self):
        """Test configuration via environment variables."""
        with patch.dict(
            os.environ,
            {
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_METRICS_ENABLED": "false",
                "LGDA_LOGGING_ENABLED": "true",
                "LGDA_JAEGER_ENDPOINT": "http://localhost:14268",
                "LGDA_HEALTH_CHECK_INTERVAL": "60",
            },
        ):
            config = LGDAConfig()

            assert config.observability_enabled is True
            assert config.metrics_enabled is False
            assert config.logging_enabled is True
            assert config.jaeger_endpoint == "http://localhost:14268"
            assert config.health_check_interval == 60

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_config_with_observability_manager(self):
        """Test that configuration properly affects observability manager."""
        with patch.dict(
            os.environ,
            {
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_METRICS_ENABLED": "true",
                "LGDA_LOGGING_ENABLED": "false",
                "LGDA_PROMETHEUS_ENDPOINT": "http://localhost:9090",
            },
        ):
            config = LGDAConfig()
            with patch("src.observability.metrics.LGDAMetrics._initialize_metrics"):
                manager = ObservabilityManager(config)

                # Metrics should be enabled
                assert manager.get_metrics().enabled is True

                # Logging should be disabled
                assert manager.get_logger().enabled is False

                # Config should be accessible
                assert manager.config.prometheus_endpoint == "http://localhost:9090"


class TestObservabilityIntegration:
    """Integration tests for full observability system."""

    @patch("src.observability.metrics.PROMETHEUS_AVAILABLE", True)
    def test_end_to_end_observability_setup(self):
        """Test complete observability setup from config to components."""
        # Configure with specific settings using environment variables
        with patch.dict(
            os.environ,
            {
                "LGDA_ENVIRONMENT": "staging",  # Use valid environment value
                "LGDA_OBSERVABILITY_ENABLED": "true",
                "LGDA_METRICS_ENABLED": "true",
                "LGDA_LOGGING_ENABLED": "true",
                "LGDA_TRACING_ENABLED": "false",  # Disable tracing for test
                "LGDA_HEALTH_MONITORING_ENABLED": "true",
                "LGDA_BUSINESS_METRICS_ENABLED": "true",
                "LGDA_HEALTH_CHECK_INTERVAL": "5",
                "LGDA_METRICS_RETENTION_HOURS": "1",
            },
        ):
            with patch("src.observability.metrics.LGDAMetrics._initialize_metrics"):
                config = LGDAConfig()

                # Setup observability
                manager = setup_observability(config)

                # Verify configuration propagated correctly
                assert manager.is_enabled() is True
                assert manager.config.health_check_interval == 5

                # Verify components are properly configured
                effective = config.effective_observability_config
                assert effective["metrics"] is True
                assert effective["logging"] is True
                assert effective["tracing"] is False
                assert effective["health_monitoring"] is True
                assert effective["business_metrics"] is True

                # Test component interactions
                metrics = manager.get_metrics()
                logger = manager.get_logger()
                health = manager.get_health_monitor()
                business = manager.get_business_metrics()

                # These should be enabled
                assert metrics.enabled is True
                assert logger.enabled is True
                assert health.enabled is True
                assert business.enabled is True

                # Test cleanup
                manager.cleanup_old_metrics()

                # Test shutdown
                manager.shutdown()

    def test_observability_disabled_integration(self):
        """Test that when disabled, all components are properly disabled."""
        with patch.dict(os.environ, {"LGDA_DISABLE_OBSERVABILITY": "true"}):
            config = LGDAConfig()
            manager = ObservabilityManager(config)

            # All components should be disabled
            assert manager.get_metrics().enabled is False
            assert manager.get_logger().enabled is False
            assert manager.get_tracer().enabled is False
            assert manager.get_health_monitor().enabled is False
            assert manager.get_business_metrics().enabled is False

            # Operations should still work (no-op)
            manager.cleanup_old_metrics()
            status = manager.get_health_status()
            summary = manager.get_metrics_summary()

            assert isinstance(status, dict)
            assert isinstance(summary, dict)
