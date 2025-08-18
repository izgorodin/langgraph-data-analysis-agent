# LGDA-003: BigQuery Client Integration

## Архитектурный контекст

Основываясь на **ADR 001** (выбор BigQuery) и **ADR 004** (fallback стратегия), BigQuery клиент - единственный источник данных:
- Синхронный интерфейс для LangGraph nodes
- Robust error handling с retry policies
- Connection pooling для производительности
- Интеграция с **ADR 003** (безопасность) через credential management

## Цель задачи
Создать production-ready BigQuery клиент с enterprise-grade надежностью, производительностью и безопасностью.

## Детальный анализ архитектуры

### 1. Authentication & Authorization
**Компонент**: Credential management
**ADR связь**: **ADR 001** - "BigQuery как единственный источник данных"

**Подводные камни**:
- Service Account key rotation
- Cross-project access permissions
- IAM role inheritance
- Local development vs production auth
- Token expiration handling

**Security Considerations**:
```python
class BigQueryAuth:
    """
    Многоуровневая аутентификация:
    1. Service Account JSON (production)
    2. Application Default Credentials (development) 
    3. User credentials (local development)
    4. Workload Identity Federation (GKE/Cloud Run)
    """

def test_auth_fallback_chain():
    """Тестирует цепочку fallback аутентификации"""
    
def test_credential_rotation():
    """Обрабатывает ротацию service account keys"""
    
def test_cross_project_access():
    """Валидирует доступ к bigquery-public-data"""
    
def test_token_expiration_handling():
    """Автоматически обновляет expired tokens"""
```

### 2. Connection Pool Management
**Компонент**: Efficient resource utilization
**Производительность**: Критично для latency

**Технические подводные камни**:
- BigQuery не использует традиционные connection pools
- Rate limiting от Google APIs
- Concurrent query limits 
- Memory management для больших результатов
- Network timeout handling

**Connection Strategy**:
```python
class BigQueryConnectionManager:
    """
    Connection management для BigQuery:
    - Single client instance с connection reuse
    - Exponential backoff для rate limits
    - Circuit breaker pattern для failures
    - Streaming для больших результатов
    """

def test_client_singleton():
    """Обеспечивает single client instance"""
    
def test_rate_limit_handling():
    """Обрабатывает Google API rate limits"""
    
def test_concurrent_query_limits():
    """Управляет concurrent queries"""
    
def test_memory_efficient_streaming():
    """Streams больших результатов"""
```

### 3. Query Execution Engine
**Компонент**: Core SQL execution logic
**ADR связь**: **ADR 003** - "Безопасное выполнение SQL"

**Execution Flow**:
1. Query validation (по LGDA-002)
2. Parameter binding (защита от injection)
3. Job submission с monitoring
4. Result streaming с pagination
5. Error handling с retry logic

**Подводные камни**:
- BigQuery job quotas и limits
- Query timeout handling (max 6 hours)
- Result set size limits (10GB uncompressed)
- Job location affinity
- Billing project management

**Critical Test Scenarios**:
```python
def test_job_submission_and_monitoring():
    """Корректно отправляет и мониторит BigQuery jobs"""
    
def test_result_pagination():
    """Обрабатывает paginated results"""
    
def test_large_result_handling():
    """Эффективно обрабатывает большие результаты"""
    
def test_query_timeout_handling():
    """Обрабатывает long-running queries"""
    
def test_job_cancellation():
    """Может отменять running jobs"""
```

### 4. Error Handling & Retry Logic
**Компонент**: Resilience engineering
**Принцип**: Graceful degradation с maximum uptime

**Error Categories**:
1. **Transient errors** - сетевые проблемы, rate limits
2. **Permanent errors** - syntax errors, permission denied  
3. **Resource errors** - quota exceeded, job limits
4. **Data errors** - table not found, schema mismatch

**Retry Strategy**:
```python
class BigQueryRetryPolicy:
    """
    Exponential backoff с jitter:
    - Transient errors: 3 retries, 2^n * 100ms delay
    - Rate limits: 5 retries, 2^n * 1s delay
    - Resource errors: 2 retries, 2^n * 5s delay
    - Permanent errors: No retry
    """

def test_transient_error_retry():
    """Retries сетевые ошибки"""
    
def test_rate_limit_backoff():
    """Exponential backoff для rate limits"""
    
def test_permanent_error_no_retry():
    """Не retries permanent errors"""
    
def test_circuit_breaker_activation():
    """Активирует circuit breaker при множественных failures"""
```

### 5. Result Processing & Type Mapping
**Компонент**: BigQuery → Python type conversion
**ADR связь**: Integration с pandas для LGDA-007

**BigQuery Type Challenges**:
- TIMESTAMP vs DATETIME vs DATE
- NUMERIC precision (38 digits)
- ARRAY и STRUCT types
- NULL handling
- Geographic types (GEOGRAPHY)
- JSON type support

**Type Mapping Strategy**:
```python
BIGQUERY_TO_PYTHON_TYPES = {
    'STRING': str,
    'INTEGER': int,
    'FLOAT': float,
    'BOOLEAN': bool,
    'TIMESTAMP': datetime,
    'DATE': date,
    'TIME': time,
    'DATETIME': datetime,
    'NUMERIC': Decimal,
    'GEOGRAPHY': str,  # WKT format
    'ARRAY': list,
    'STRUCT': dict,
    'JSON': dict,
}

def test_type_conversion_accuracy():
    """Корректно конвертирует BigQuery types"""
    
def test_null_value_handling():
    """Обрабатывает NULL values"""
    
def test_array_struct_processing():
    """Обрабатывает сложные nested types"""
    
def test_precision_preservation():
    """Сохраняет precision для NUMERIC"""
```

## Архитектурная интеграция

### Integration с LangGraph Node
```python
def execute_sql_node(state: AgentState) -> AgentState:
    """
    Входные данные: state.sql (валидированный SQL)
    Обработка: 
        1. Execute query через BigQuery client
        2. Convert results to pandas DataFrame
        3. Handle errors gracefully
    Выходные данные:
        - state.dataframe (результаты)
        - state.error (если ошибка)
        - state.metadata (query stats)
    """
```

### Configuration Management
**Компонент**: Environment-aware configuration

```python
@dataclass
class BigQueryConfig:
    """Configuration для BigQuery client"""
    project_id: str
    dataset_id: str = "bigquery-public-data.thelook_ecommerce"
    location: str = "US"
    query_timeout: int = 300  # 5 minutes default
    max_results: int = 1000   # Sync with ADR 003 LIMIT
    job_retry_count: int = 3
    rate_limit_retry_count: int = 5
    
def test_config_validation():
    """Валидирует configuration parameters"""
    
def test_environment_specific_config():
    """Разные настройки для dev/staging/production"""
```

### Monitoring & Observability
**Компонент**: Production monitoring hooks

```python
class BigQueryMetrics:
    """Метрики для monitoring"""
    query_execution_time: float
    result_row_count: int
    bytes_processed: int
    bytes_billed: int
    job_id: str
    cache_hit: bool
    
def test_metrics_collection():
    """Собирает execution metrics"""
    
def test_performance_logging():
    """Логирует performance data"""
```

## Performance Optimization

### Query Performance
**Targets**:
- Simple queries (< 1000 rows): < 2 seconds
- Complex queries (< 10K rows): < 10 seconds  
- Aggregation queries: < 30 seconds
- Cache hit ratio: > 80%

**Optimization Techniques**:
```python
def test_query_caching():
    """Использует BigQuery query cache"""
    
def test_result_streaming():
    """Streams results для больших datasets"""
    
def test_partition_pruning():
    """Optimizes partitioned table queries"""
```

### Resource Management
```python
def test_memory_usage_monitoring():
    """Мониторит memory usage"""
    
def test_connection_cleanup():
    """Правильно cleanup connections"""
    
def test_job_resource_tracking():
    """Tracks BigQuery job resources"""
```

## Структура тестов

```
tests/unit/bigquery/
├── test_authentication.py        # Auth scenarios
├── test_connection_management.py # Connection pooling
├── test_query_execution.py       # Core execution logic  
├── test_error_handling.py        # Error scenarios
├── test_retry_logic.py           # Retry policies
├── test_type_conversion.py       # Result processing
├── test_performance.py           # Performance benchmarks
└── test_monitoring.py            # Metrics collection

tests/integration/bigquery/
├── test_real_queries.py          # Actual BigQuery calls
├── test_large_datasets.py        # Performance with big data
├── test_concurrent_access.py     # Multiple simultaneous queries
└── test_error_scenarios.py       # Real error conditions

tests/fixtures/bigquery/
├── sample_queries.sql            # Test queries
├── expected_results.json         # Expected outputs
└── error_responses.json          # Error scenarios
```

## Production Deployment Considerations

### Security Hardening
```python
def test_credential_security():
    """Credentials не логируются"""
    
def test_query_sanitization():
    """SQL queries sanitized в logs"""
    
def test_audit_logging():
    """Audit trail для data access"""
```

### Disaster Recovery
```python
def test_regional_failover():
    """Handles BigQuery region failures"""
    
def test_quota_exhaustion():
    """Graceful handling quota limits"""
    
def test_service_degradation():
    """Handles BigQuery service issues"""
```

## Критерии приемки

- [ ] Успешная аутентификация во всех environments
- [ ] Query execution < 2s для simple queries
- [ ] Error handling covers все BigQuery error types
- [ ] Type conversion 100% accurate
- [ ] Memory usage остается < 100MB для типичных queries
- [ ] Concurrent queries поддерживаются (до 5 simultaneous)
- [ ] Monitoring hooks работают корректно
- [ ] Integration тесты проходят с real BigQuery

## Возможные сложности

### 1. BigQuery Quotas & Limits
**Проблема**: Query slots, concurrent queries, daily limits
**Решение**: Queue management, graceful degradation, monitoring

### 2. Network Reliability
**Проблема**: Intermittent network issues, DNS problems
**Решение**: Robust retry logic, circuit breaker, health checks

### 3. Large Result Sets
**Проблема**: Memory exhaustion, network timeouts
**Решение**: Streaming, pagination, result size limits

### 4. Cost Management
**Проблема**: Expensive queries, unexpected billing
**Решение**: Query cost estimation, dry-run validation, budgets

## Метрики производительности

- Query latency: p50 < 1s, p95 < 5s, p99 < 30s
- Error rate: < 1%
- Cache hit rate: > 80%
- Memory efficiency: < 100MB для 95% queries
- Concurrent query capacity: 5+ simultaneous
- Uptime: 99.9%

## Integration Points

- **Зависит от**: LGDA-001 (test infrastructure), LGDA-002 (SQL validation)  
- **Используется в**: LGDA-006 (LangGraph nodes), LGDA-007 (pandas integration)
- **Критично для**: LGDA-010 (integration tests), LGDA-012 (production deployment)
