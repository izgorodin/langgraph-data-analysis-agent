# LGDA Production Observability

This document describes the comprehensive observability infrastructure implemented for the LangGraph Data Analysis Agent (LGDA).

## Overview

The observability system provides production-grade monitoring, metrics collection, structured logging, distributed tracing, health monitoring, and business intelligence tracking for LGDA.

### Key Features

- **Zero Performance Impact**: Can be completely disabled via configuration
- **Graceful Degradation**: Works even when optional dependencies are missing
- **Unified Configuration**: Centrally managed through the LGDA configuration system
- **Production Ready**: Designed for high-availability production environments

## Quick Start

### Basic Setup

```python
from src.observability import setup_observability
from src.config import LGDAConfig

# Basic setup with defaults
config = LGDAConfig()
observability = setup_observability(config)

# Use observability components
metrics = observability.get_metrics()
logger = observability.get_logger()
```

### Environment Configuration

Control observability via environment variables:

```bash
# Enable/disable observability globally
export LGDA_OBSERVABILITY_ENABLED=true
export LGDA_DISABLE_OBSERVABILITY=false  # Override flag

# Control individual components
export LGDA_METRICS_ENABLED=true
export LGDA_LOGGING_ENABLED=true
export LGDA_TRACING_ENABLED=false
export LGDA_HEALTH_MONITORING_ENABLED=true
export LGDA_BUSINESS_METRICS_ENABLED=true

# Configure observability endpoints
export LGDA_PROMETHEUS_ENDPOINT=http://localhost:9090
export LGDA_JAEGER_ENDPOINT=http://localhost:14268

# Tune observability behavior
export LGDA_HEALTH_CHECK_INTERVAL=30
export LGDA_METRICS_RETENTION_HOURS=24
```

## Components

### 1. Metrics Collection (`LGDAMetrics`)

Prometheus-compatible metrics collection with automatic instrumentation:

- **Performance Metrics**: Request duration, throughput, error rates
- **Business Metrics**: Query success rates, insight quality, user satisfaction
- **Resource Metrics**: Memory usage, CPU usage, BigQuery costs
- **System Metrics**: Active connections, component health

```python
from src.observability import get_observability_manager

manager = get_observability_manager()
metrics = manager.get_metrics()

# Record custom metrics
metrics.record_request("my_endpoint", "success", 1.5)
metrics.record_query_execution(True, bytes_processed=1000000)
```

### 2. Structured Logging (`LGDALogger`)

Correlation-aware structured logging with audit trails:

- **Request Correlation**: Automatic correlation IDs across requests
- **Context Preservation**: User, session, and execution context
- **Audit Trails**: Security events, data access, configuration changes
- **Error Details**: Stack traces, recovery actions, error context

```python
from src.observability.logging import get_logger, set_request_context

logger = get_logger()

# Set correlation context
with set_request_context(request_id="req-123", user_id="user-456"):
    logger.log_query_execution(
        question="Sales by region",
        sql="SELECT region, SUM(revenue) FROM sales GROUP BY region",
        execution_time=2.3,
        success=True
    )
```

### 3. Distributed Tracing (`LGDATracer`)

OpenTelemetry-based distributed tracing:

- **End-to-End Visibility**: Trace requests across all components
- **Performance Profiling**: Identify bottlenecks and optimization opportunities
- **Error Correlation**: Link errors across distributed components
- **Dependency Mapping**: Understand service interactions

```python
from src.observability.tracing import get_tracer

tracer = get_tracer()

# Trace operations
with tracer.trace_pipeline_execution("Analyze customer behavior") as span:
    span.set_attribute("complexity", "high")
    # Your pipeline logic here
```

### 4. Health Monitoring (`HealthMonitor`)

Comprehensive health checks and system monitoring:

- **System Health**: Memory, CPU, disk usage monitoring
- **Dependency Health**: BigQuery, LLM provider connectivity
- **Component Health**: Pipeline component status
- **Automatic Alerting**: Health threshold monitoring

```python
from src.observability.health import get_health_monitor

health = get_health_monitor()

# Check system health
status = health.get_overall_health()
print(f"System Status: {status['status']}")

# Add custom health checks
health.register_health_check("custom_service", my_health_check_func)
```

### 5. Business Metrics (`BusinessMetrics`)

Business intelligence and usage analytics:

- **User Behavior**: Query patterns, session analytics, feature usage
- **Query Analysis**: Success rates, complexity distribution, cost efficiency
- **Quality Metrics**: Insight quality scores, user satisfaction
- **ROI Measurement**: Cost per insight, value generation tracking

```python
from src.observability.business_metrics import get_business_metrics

business = get_business_metrics()

# Track business events
business.track_query_success_rate(
    success=True,
    question="Monthly revenue trends",
    complexity=QueryComplexity.MEDIUM
)

business.track_insight_quality(
    feedback_score=0.85,
    question="Customer segmentation analysis",
    user_rating=4
)
```

## Integration with Pipeline

### Instrumented Nodes

The observability system provides instrumented versions of all pipeline nodes:

```python
from src.observability.instrumented_nodes import INSTRUMENTED_NODES

# Get instrumented versions
instrumented_plan = INSTRUMENTED_NODES["plan"]
instrumented_execute_sql = INSTRUMENTED_NODES["execute_sql"]

# Or use the helper
from src.observability.instrumented_nodes import get_instrumented_node
instrumented_node = get_instrumented_node("plan")
```

### Automatic Instrumentation

When enabled, all pipeline operations are automatically instrumented with:

- **Timing Metrics**: Execution duration for each stage
- **Success/Failure Tracking**: Error rates and recovery metrics
- **Resource Usage**: Memory and CPU consumption
- **Business Metrics**: User patterns and query analysis

## Configuration Management

### Unified Configuration

Observability integrates with the LGDA configuration system:

```python
from src.config import LGDAConfig

config = LGDAConfig()

# Check observability status
print(f"Observability enabled: {config.is_observability_enabled}")
print(f"Effective config: {config.effective_observability_config}")

# Access observability settings
print(f"Prometheus endpoint: {config.prometheus_endpoint}")
print(f"Health check interval: {config.health_check_interval}")
```

### Environment Variables

Complete list of observability environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LGDA_OBSERVABILITY_ENABLED` | `true` | Enable observability globally |
| `LGDA_DISABLE_OBSERVABILITY` | `false` | Override flag to disable everything |
| `LGDA_METRICS_ENABLED` | `true` | Enable Prometheus metrics |
| `LGDA_LOGGING_ENABLED` | `true` | Enable structured logging |
| `LGDA_TRACING_ENABLED` | `true` | Enable distributed tracing |
| `LGDA_HEALTH_MONITORING_ENABLED` | `true` | Enable health monitoring |
| `LGDA_BUSINESS_METRICS_ENABLED` | `true` | Enable business metrics |
| `LGDA_PROMETHEUS_ENDPOINT` | `None` | Prometheus server endpoint |
| `LGDA_JAEGER_ENDPOINT` | `None` | Jaeger collector endpoint |
| `LGDA_HEALTH_CHECK_INTERVAL` | `30` | Health check interval (seconds) |
| `LGDA_METRICS_RETENTION_HOURS` | `24` | Metrics retention period |

## Production Deployment

### Prometheus Integration

1. **Configure Prometheus** to scrape metrics from your LGDA application
2. **Set up Grafana** dashboards for visualization
3. **Configure AlertManager** for alerting on metric thresholds

### Jaeger Integration

1. **Deploy Jaeger** collector and UI
2. **Set `LGDA_JAEGER_ENDPOINT`** to your Jaeger collector
3. **Configure sampling** for production load

### Log Aggregation

1. **Configure structured logging** output format
2. **Set up log aggregation** (ELK stack, Fluentd, etc.)
3. **Create log-based alerts** for error patterns

### Health Monitoring

1. **Configure health check endpoints** for load balancers
2. **Set up external monitoring** (Nagios, Datadog, etc.)
3. **Configure alerting** for component failures

## Performance Considerations

### Zero Impact When Disabled

```bash
# Completely disable observability
export LGDA_DISABLE_OBSERVABILITY=true
```

When disabled, observability components:
- Return immediately from all methods
- Have zero memory overhead
- Add no CPU overhead
- Don't create any network connections

### Minimal Impact When Enabled

- **Metrics Collection**: < 1ms overhead per operation
- **Structured Logging**: Asynchronous logging to avoid blocking
- **Distributed Tracing**: Sampling-based to reduce overhead
- **Health Monitoring**: Background thread with configurable intervals

### Memory Management

- **Automatic Cleanup**: Old metrics are automatically cleaned up
- **Configurable Retention**: Control memory usage via retention settings
- **Buffered Operations**: Reduce I/O overhead with buffering

## Troubleshooting

### Common Issues

1. **Prometheus metrics not appearing**
   - Check `LGDA_METRICS_ENABLED=true`
   - Verify prometheus_client is installed
   - Check application logs for initialization errors

2. **Tracing not working**
   - Check `LGDA_TRACING_ENABLED=true`  
   - Verify OpenTelemetry dependencies
   - Check Jaeger endpoint configuration

3. **Health checks failing**
   - Check system resource availability
   - Verify dependency connectivity
   - Review health check interval settings

### Debug Mode

Enable debug logging to troubleshoot observability issues:

```python
import logging
logging.getLogger('src.observability').setLevel(logging.DEBUG)
```

### Test Configuration

Verify observability configuration:

```python
from src.observability import get_observability_manager

manager = get_observability_manager()
print(f"Observability enabled: {manager.is_enabled()}")
print(f"Components: {list(manager.get_all_components().keys())}")

# Test each component
for name, component in manager.get_all_components().items():
    print(f"{name}: enabled={getattr(component, 'enabled', 'N/A')}")
```

## Best Practices

### 1. Use Correlation IDs

Always set correlation context for request tracking:

```python
from src.observability.logging import set_request_context

with set_request_context(request_id=request_id, user_id=user_id):
    # Your application logic
    pass
```

### 2. Monitor Business Metrics

Track business value, not just technical metrics:

```python
business_metrics.track_resource_efficiency(
    query_cost=0.05,  # BigQuery cost
    insight_value=0.8  # Business value score
)
```

### 3. Set Up Alerting

Configure alerts for key metrics:
- Error rate > 5%
- Response time P95 > 60 seconds
- System health degraded
- Cost efficiency below threshold

### 4. Regular Cleanup

Schedule regular cleanup of old metrics:

```python
manager.cleanup_old_metrics()  # Cleans up based on retention settings
```

### 5. Performance Testing

Test observability overhead in your environment:

```python
# Measure with and without observability
import time
start = time.time()
# Your operations
duration = time.time() - start
```

## Contributing

When adding new observability features:

1. **Follow the existing patterns** for component structure
2. **Add comprehensive tests** with mocking for external dependencies
3. **Ensure graceful degradation** when dependencies are missing
4. **Update configuration** with new environment variables
5. **Document new features** in this README

## References

- [Prometheus Client Documentation](https://prometheus.io/docs/guides/instrumenting/)
- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [Structured Logging Best Practices](https://engineering.fb.com/2019/10/07/developer-tools/logging/)
- [Health Check Patterns](https://microservices.io/patterns/observability/health-check-api.html)