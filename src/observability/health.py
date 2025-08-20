"""Health monitoring for LGDA production observability.

Provides system health checks, dependency health monitoring, circuit breaker
status tracking, and resource availability monitoring.

Can be disabled via LGDA_DISABLE_OBSERVABILITY environment variable.
"""

import os
import time
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# psutil is optional - graceful degradation if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available, system health checks disabled")

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentHealth:
    """Health status for a specific component."""
    
    def __init__(self, name: str, status: HealthStatus, 
                 message: str = "", details: Optional[Dict[str, Any]] = None,
                 last_check: Optional[float] = None):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.last_check = last_check or time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "last_check": self.last_check,
            "age_seconds": time.time() - self.last_check
        }


class HealthMonitor:
    """Production-grade health monitoring for LGDA components.
    
    Provides comprehensive health checks with graceful degradation when
    monitoring is disabled or dependencies are not available.
    """
    
    def __init__(self, enabled: Optional[bool] = None, check_interval: int = 30):
        """Initialize health monitor.
        
        Args:
            enabled: Override default enabled state. If None, uses environment.
            check_interval: Interval between automatic health checks (seconds).
        """
        if enabled is None:
            # Check for disable flag
            self.enabled = not os.getenv("LGDA_DISABLE_OBSERVABILITY", "false").lower() == "true"
        else:
            self.enabled = enabled
            
        self.check_interval = check_interval
        self.health_checks: Dict[str, Callable[[], ComponentHealth]] = {}
        self.last_results: Dict[str, ComponentHealth] = {}
        self._lock = threading.RLock()
        self._background_thread = None
        self._shutdown_event = threading.Event()
        
        if not self.enabled:
            logger.info("LGDA health monitoring disabled")
            return
            
        try:
            self._register_default_checks()
            self._start_background_monitoring()
            logger.info("LGDA health monitoring initialized")
        except Exception as e:
            logger.error(f"Failed to initialize health monitoring: {e}")
            self.enabled = False
    
    def _register_default_checks(self):
        """Register default system health checks."""
        if PSUTIL_AVAILABLE:
            self.register_health_check("system_memory", self._check_system_memory)
            self.register_health_check("system_disk", self._check_system_disk)
            self.register_health_check("system_cpu", self._check_system_cpu)
        else:
            logger.info("System health checks disabled - psutil not available")
    
    def _start_background_monitoring(self):
        """Start background thread for periodic health checks."""
        if self._background_thread is None or not self._background_thread.is_alive():
            self._shutdown_event.clear()
            self._background_thread = threading.Thread(
                target=self._background_monitor,
                daemon=True
            )
            self._background_thread.start()
    
    def _background_monitor(self):
        """Background monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                self.check_all_health()
            except Exception as e:
                logger.error(f"Background health check failed: {e}")
                
            # Wait for interval or shutdown
            self._shutdown_event.wait(self.check_interval)
    
    def register_health_check(self, name: str, check_func: Callable[[], ComponentHealth]):
        """Register a health check function.
        
        Args:
            name: Unique name for the health check.
            check_func: Function that returns ComponentHealth.
        """
        if not self.enabled:
            return
            
        with self._lock:
            self.health_checks[name] = check_func
            logger.debug(f"Registered health check: {name}")
    
    def check_component_health(self, name: str) -> ComponentHealth:
        """Check health of a specific component."""
        if not self.enabled:
            return ComponentHealth(name, HealthStatus.UNKNOWN, "Monitoring disabled")
            
        with self._lock:
            if name not in self.health_checks:
                return ComponentHealth(name, HealthStatus.UNKNOWN, "No health check registered")
            
            try:
                result = self.health_checks[name]()
                self.last_results[name] = result
                return result
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                result = ComponentHealth(name, HealthStatus.UNHEALTHY, f"Check failed: {e}")
                self.last_results[name] = result
                return result
    
    def check_all_health(self, timeout: int = 10) -> Dict[str, ComponentHealth]:
        """Check health of all registered components with timeout."""
        if not self.enabled:
            return {}
            
        results = {}
        
        with self._lock:
            check_names = list(self.health_checks.keys())
        
        # Run health checks in parallel with timeout
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_name = {
                executor.submit(self.check_component_health, name): name 
                for name in check_names
            }
            
            for future in as_completed(future_to_name, timeout=timeout):
                name = future_to_name[future]
                try:
                    result = future.result()
                    results[name] = result
                except Exception as e:
                    logger.error(f"Health check timeout for {name}: {e}")
                    results[name] = ComponentHealth(
                        name, HealthStatus.UNHEALTHY, f"Timeout: {e}"
                    )
        
        return results
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        if not self.enabled:
            return {
                "status": HealthStatus.UNKNOWN.value,
                "message": "Health monitoring disabled",
                "components": {},
                "timestamp": time.time()
            }
        
        # Get fresh health checks
        component_health = self.check_all_health()
        
        # Determine overall status
        if not component_health:
            overall_status = HealthStatus.UNKNOWN
            message = "No components monitored"
        else:
            statuses = [health.status for health in component_health.values()]
            if all(status == HealthStatus.HEALTHY for status in statuses):
                overall_status = HealthStatus.HEALTHY
                message = "All components healthy"
            elif any(status == HealthStatus.UNHEALTHY for status in statuses):
                overall_status = HealthStatus.UNHEALTHY
                unhealthy_components = [
                    name for name, health in component_health.items()
                    if health.status == HealthStatus.UNHEALTHY
                ]
                message = f"Unhealthy components: {', '.join(unhealthy_components)}"
            else:
                overall_status = HealthStatus.DEGRADED
                message = "Some components degraded"
        
        return {
            "status": overall_status.value,
            "message": message,
            "components": {name: health.to_dict() for name, health in component_health.items()},
            "timestamp": time.time()
        }
    
    def _check_system_memory(self) -> ComponentHealth:
        """Check system memory usage."""
        if not PSUTIL_AVAILABLE:
            return ComponentHealth(
                "system_memory", HealthStatus.UNKNOWN, "psutil not available"
            )
            
        try:
            memory = psutil.virtual_memory()
            usage_percent = memory.percent
            
            if usage_percent < 80:
                status = HealthStatus.HEALTHY
                message = f"Memory usage: {usage_percent:.1f}%"
            elif usage_percent < 90:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {usage_percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Critical memory usage: {usage_percent:.1f}%"
            
            details = {
                "usage_percent": usage_percent,
                "available_gb": memory.available / (1024**3),
                "total_gb": memory.total / (1024**3)
            }
            
            return ComponentHealth("system_memory", status, message, details)
            
        except Exception as e:
            return ComponentHealth(
                "system_memory", HealthStatus.UNHEALTHY, f"Memory check failed: {e}"
            )
    
    def _check_system_disk(self) -> ComponentHealth:
        """Check system disk usage."""
        if not PSUTIL_AVAILABLE:
            return ComponentHealth(
                "system_disk", HealthStatus.UNKNOWN, "psutil not available"
            )
            
        try:
            disk = psutil.disk_usage('/')
            usage_percent = (disk.used / disk.total) * 100
            
            if usage_percent < 80:
                status = HealthStatus.HEALTHY
                message = f"Disk usage: {usage_percent:.1f}%"
            elif usage_percent < 90:
                status = HealthStatus.DEGRADED
                message = f"High disk usage: {usage_percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Critical disk usage: {usage_percent:.1f}%"
            
            details = {
                "usage_percent": usage_percent,
                "free_gb": disk.free / (1024**3),
                "total_gb": disk.total / (1024**3)
            }
            
            return ComponentHealth("system_disk", status, message, details)
            
        except Exception as e:
            return ComponentHealth(
                "system_disk", HealthStatus.UNHEALTHY, f"Disk check failed: {e}"
            )
    
    def _check_system_cpu(self) -> ComponentHealth:
        """Check system CPU usage."""
        if not PSUTIL_AVAILABLE:
            return ComponentHealth(
                "system_cpu", HealthStatus.UNKNOWN, "psutil not available"
            )
            
        try:
            # Get CPU usage over 1 second interval
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent < 80:
                status = HealthStatus.HEALTHY
                message = f"CPU usage: {cpu_percent:.1f}%"
            elif cpu_percent < 90:
                status = HealthStatus.DEGRADED
                message = f"High CPU usage: {cpu_percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Critical CPU usage: {cpu_percent:.1f}%"
            
            details = {
                "usage_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
            
            return ComponentHealth("system_cpu", status, message, details)
            
        except Exception as e:
            return ComponentHealth(
                "system_cpu", HealthStatus.UNHEALTHY, f"CPU check failed: {e}"
            )
    
    def add_bigquery_health_check(self, bq_client_func: Callable):
        """Add BigQuery connectivity health check."""
        def check_bigquery():
            try:
                client = bq_client_func()
                # Simple query to test connectivity
                query = "SELECT 1 as test_connection"
                job = client.query(query, timeout=5)
                list(job.result())  # Execute query
                
                return ComponentHealth(
                    "bigquery", HealthStatus.HEALTHY, "BigQuery connection successful"
                )
            except Exception as e:
                return ComponentHealth(
                    "bigquery", HealthStatus.UNHEALTHY, f"BigQuery connection failed: {e}"
                )
        
        self.register_health_check("bigquery", check_bigquery)
    
    def add_llm_health_check(self, llm_test_func: Callable):
        """Add LLM provider health check."""
        def check_llm():
            try:
                # Test simple LLM request
                response = llm_test_func("test")
                if response and len(response) > 0:
                    return ComponentHealth(
                        "llm", HealthStatus.HEALTHY, "LLM provider responsive"
                    )
                else:
                    return ComponentHealth(
                        "llm", HealthStatus.DEGRADED, "LLM provider returned empty response"
                    )
            except Exception as e:
                return ComponentHealth(
                    "llm", HealthStatus.UNHEALTHY, f"LLM provider failed: {e}"
                )
        
        self.register_health_check("llm", check_llm)
    
    def shutdown(self):
        """Shutdown health monitoring."""
        if self._background_thread and self._background_thread.is_alive():
            self._shutdown_event.set()
            self._background_thread.join(timeout=5)


# Global health monitor instance for convenience
_global_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance, initializing if needed."""
    global _global_health_monitor
    if _global_health_monitor is None:
        _global_health_monitor = HealthMonitor()
    return _global_health_monitor


def disable_health_monitoring():
    """Disable health monitoring globally."""
    global _global_health_monitor
    if _global_health_monitor:
        _global_health_monitor.shutdown()
    _global_health_monitor = HealthMonitor(enabled=False)