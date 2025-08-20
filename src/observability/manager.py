"""Integration between LGDA configuration and observability components.

This module provides easy setup and configuration of all observability components
using the unified LGDA configuration system.
"""

from typing import Optional, Dict, Any
import logging

from ..config import LGDAConfig
from .metrics import LGDAMetrics
from .logging import LGDALogger
from .tracing import LGDATracer
from .health import HealthMonitor
from .business_metrics import BusinessMetrics

logger = logging.getLogger(__name__)


class ObservabilityManager:
    """Central manager for all observability components with unified configuration."""
    
    def __init__(self, config: Optional[LGDAConfig] = None):
        """Initialize observability manager with configuration.
        
        Args:
            config: LGDA configuration instance. If None, creates a new one.
        """
        self.config = config or LGDAConfig()
        self.components: Dict[str, Any] = {}
        
        # Initialize components based on configuration
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize observability components based on configuration."""
        effective_config = self.config.effective_observability_config
        
        # Initialize metrics
        if effective_config["metrics"]:
            self.components["metrics"] = LGDAMetrics(enabled=True)
            logger.info("Metrics collection enabled")
        else:
            self.components["metrics"] = LGDAMetrics(enabled=False)
            logger.info("Metrics collection disabled")
        
        # Initialize structured logging
        if effective_config["logging"]:
            self.components["logging"] = LGDALogger(enabled=True)
            logger.info("Structured logging enabled")
        else:
            self.components["logging"] = LGDALogger(enabled=False)
            logger.info("Structured logging disabled")
        
        # Initialize distributed tracing
        if effective_config["tracing"]:
            self.components["tracing"] = LGDATracer(
                enabled=True,
                jaeger_endpoint=self.config.jaeger_endpoint
            )
            logger.info("Distributed tracing enabled")
        else:
            self.components["tracing"] = LGDATracer(enabled=False)
            logger.info("Distributed tracing disabled")
        
        # Initialize health monitoring
        if effective_config["health_monitoring"]:
            self.components["health"] = HealthMonitor(
                enabled=True,
                check_interval=self.config.health_check_interval
            )
            logger.info("Health monitoring enabled")
        else:
            self.components["health"] = HealthMonitor(enabled=False)
            logger.info("Health monitoring disabled")
        
        # Initialize business metrics
        if effective_config["business_metrics"]:
            self.components["business_metrics"] = BusinessMetrics(enabled=True)
            logger.info("Business metrics enabled")
        else:
            self.components["business_metrics"] = BusinessMetrics(enabled=False)
            logger.info("Business metrics disabled")
    
    def get_metrics(self) -> LGDAMetrics:
        """Get the metrics component."""
        return self.components["metrics"]
    
    def get_logger(self) -> LGDALogger:
        """Get the logging component."""
        return self.components["logging"]
    
    def get_tracer(self) -> LGDATracer:
        """Get the tracing component."""
        return self.components["tracing"]
    
    def get_health_monitor(self) -> HealthMonitor:
        """Get the health monitoring component."""
        return self.components["health"]
    
    def get_business_metrics(self) -> BusinessMetrics:
        """Get the business metrics component."""
        return self.components["business_metrics"]
    
    def get_all_components(self) -> Dict[str, Any]:
        """Get all observability components."""
        return self.components.copy()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        health_monitor = self.get_health_monitor()
        return health_monitor.get_overall_health()
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get business metrics summary."""
        business_metrics = self.get_business_metrics()
        return business_metrics.get_metrics_summary(hours=hours)
    
    def configure_bigquery_health_check(self, bq_client_func):
        """Configure BigQuery health check."""
        health_monitor = self.get_health_monitor()
        health_monitor.add_bigquery_health_check(bq_client_func)
    
    def configure_llm_health_check(self, llm_test_func):
        """Configure LLM provider health check."""
        health_monitor = self.get_health_monitor()
        health_monitor.add_llm_health_check(llm_test_func)
    
    def cleanup_old_metrics(self):
        """Clean up old metrics to manage memory."""
        business_metrics = self.get_business_metrics()
        business_metrics.clear_metrics_buffer(
            older_than_hours=self.config.metrics_retention_hours
        )
    
    def is_enabled(self) -> bool:
        """Check if observability is enabled overall."""
        return self.config.is_observability_enabled
    
    def shutdown(self):
        """Shutdown all observability components."""
        health_monitor = self.get_health_monitor()
        health_monitor.shutdown()
        logger.info("Observability components shut down")


# Global observability manager instance
_global_observability_manager: Optional[ObservabilityManager] = None


def get_observability_manager(config: Optional[LGDAConfig] = None) -> ObservabilityManager:
    """Get the global observability manager instance.
    
    Args:
        config: Configuration to use. If None and no global instance exists,
                creates a new config.
    
    Returns:
        ObservabilityManager instance.
    """
    global _global_observability_manager
    
    if _global_observability_manager is None:
        _global_observability_manager = ObservabilityManager(config)
    elif config is not None:
        # If a new config is provided, reinitialize
        _global_observability_manager = ObservabilityManager(config)
    
    return _global_observability_manager


def setup_observability(config: Optional[LGDAConfig] = None) -> ObservabilityManager:
    """Setup observability with the given configuration.
    
    This is a convenience function that creates and configures the observability
    manager with the provided configuration.
    
    Args:
        config: LGDA configuration. If None, uses environment variables.
    
    Returns:
        Configured ObservabilityManager instance.
    """
    manager = ObservabilityManager(config)
    
    # Set system info in metrics
    metrics = manager.get_metrics()
    metrics.set_system_info({
        "version": "1.0.0",
        "environment": config.environment if config else "unknown",
        "observability_enabled": str(manager.is_enabled())
    })
    
    return manager


def shutdown_observability():
    """Shutdown the global observability manager."""
    global _global_observability_manager
    if _global_observability_manager:
        _global_observability_manager.shutdown()
        _global_observability_manager = None