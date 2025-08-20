# LGDA-007: Unified Retry Architecture Implementation

**Priority**: HIGH | **Type**: Architecture | **Parallel**: Can run with LGDA-008, LGDA-009

## Архитектурный контекст
На базе ADR-001 (Unified Retry Architecture) необходимо консолидировать двойную ретрай-логику, которая сейчас разбросана между `bq.py` и механизмом ретраев в LangGraph.

## Цель задачи
Реализовать централизованную настраиваемую систему ретраев, которая устраняет дублирование логики и обеспечивает единообразную обработку ошибок во всех компонентах.

## Детальный анализ

### Current Problem
- **Dual retry systems**: `bq.py` has exponential backoff retry, LangGraph has SQL validation retry
- **Inconsistent behavior**: Different retry strategies, timeouts, and error classifications
- **Resource waste**: Double processing on SQL generation errors
- **Poor UX**: Hanging processes, duplicate error messages

### Solution Architecture
```python
# src/core/retry.py
class RetryStrategy:
    def __init__(self, max_attempts: int, base_delay: float, max_delay: float,
                 backoff_multiplier: float = 2.0, jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter

class RetryConfig:
    SQL_GENERATION = RetryStrategy(max_attempts=3, base_delay=1.0, max_delay=8.0)
    BIGQUERY_TRANSIENT = RetryStrategy(max_attempts=5, base_delay=0.5, max_delay=30.0)
    LLM_TIMEOUT = RetryStrategy(max_attempts=2, base_delay=2.0, max_delay=10.0)

@retry_with_strategy(RetryConfig.SQL_GENERATION)
async def retry_sql_generation(state: AgentState, error_context: str) -> str:
    # Consolidated SQL retry with error context
```

### Implementation Components

1. **Core Retry Module** (`src/core/retry.py`)
   - Unified retry decorator with configurable strategies
   - Error classification system (transient, permanent, rate-limit)
   - Circuit breaker integration
   - Metrics collection

2. **LangGraph Integration** (`src/agent/graph.py`)
   - Remove manual retry logic from conditional edges
   - Integrate with unified retry system
   - Preserve state consistency during retries

3. **BigQuery Integration** (`src/bq.py`)
   - Migrate existing retry logic to unified system
   - Maintain backward compatibility
   - Enhanced error context propagation

4. **Configuration** (`src/config.py`)
   - Centralized retry configuration
   - Environment-specific overrides
   - Runtime configurability

### Dependencies
- **After**: Must review current retry logic in both systems
- **Before**: LGDA-008 (Configuration Management) can run in parallel
- **Parallel with**: LGDA-009 (Error Handling), LGDA-010 (Test Infrastructure)

## Критерии приемки

### Functional Requirements
- ✅ Single retry system handles all retry scenarios
- ✅ Configurable retry strategies per operation type
- ✅ Error context propagated through retry attempts
- ✅ Circuit breaker prevents cascade failures
- ✅ No duplicate processing or hanging operations

### Non-Functional Requirements
- ✅ Zero breaking changes to existing API
- ✅ Performance overhead < 5ms per operation
- ✅ Memory usage stable during retry storms
- ✅ All existing tests pass
- ✅ New retry scenarios covered by tests

### Integration Tests
```python
def test_sql_generation_retry_with_bigquery_error():
    """SQL generation retries on BigQuery validation errors"""

def test_circuit_breaker_prevents_retry_storms():
    """Circuit breaker activates after threshold failures"""

def test_retry_context_preservation():
    """Error context accumulates across retry attempts"""
```

## Возможные сложности
- Конфликт стратегий ретраев между LangGraph и BigQuery
- Классификация постоянных vs временных ошибок (false positive/negative)
- Тюнинг backoff и jitter без деградации UX и времени ответа
- Корректная отмена задач, очистка состояния и предотвращение утечек ресурсов
- Предотвращение retry storm; координация с circuit breaker и лимитами провайдеров

## Integration Points
Взаимодействует с LGDA-008 (единая конфигурация ретраев), LGDA-009 (классификация ошибок и стратегии восстановления),
LGDA-011 (метрики/трейсинг ретраев, алерты), LGDA-012 (ограничение конкуренции и ресурс-менеджмент).
Также учесть безопасность (LGDA-013): security-ошибки классифицируются как постоянные (без ретраев), исключить утечки секретов в логах.

## Rollback Plan
1. Feature flag: `LGDA_USE_UNIFIED_RETRY=false`
2. Gradual migration: SQL retry first, then BigQuery
3. Monitoring: Track retry metrics before/after
4. Automatic rollback: >10% error rate increase triggers revert

## Estimated Effort
**3-4 days** | **Files**: ~8 | **Tests**: ~15 new

## Parallel Execution Notes
- Can work alongside LGDA-008 (different files)
- Coordinate with LGDA-009 on error handling interfaces
- Test infrastructure (LGDA-010) can develop retry test patterns simultaneously
