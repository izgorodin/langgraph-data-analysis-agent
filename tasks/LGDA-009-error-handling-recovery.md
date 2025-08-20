# LGDA-009: Error Handling and Recovery

**Priority**: HIGH | **Type**: Reliability | **Parallel**: Can run with LGDA-007, LGDA-008

## Architectural Context
Based on **ADR-003** (Error Handling Strategy), we need to eliminate hanging processes, provide proper error recovery, and ensure production-grade reliability.

## Objective
Implement comprehensive error handling with graceful degradation, prevent hanging processes, and provide actionable error messages for both users and developers.

## Detailed Analysis

### Current Problems
- **Hanging processes**: System hangs on BigQuery Array null element errors
- **Silent failures**: Errors not propagated properly through LangGraph
- **Duplicate reports**: Error states cause report duplication
- **Poor error UX**: Technical errors shown to business users
- **Insufficient monitoring**: No error tracking or alerting

### Solution Architecture
```python
# src/error/core.py
class LGDAError(Exception):
    """Base exception with error context"""
    def __init__(self, message: str, error_code: str, context: Dict[str, Any]):
        self.message = message
        self.error_code = error_code
        self.context = context
        self.timestamp = datetime.utcnow()
        super().__init__(message)

class SqlGenerationError(LGDAError):
    """SQL generation specific errors"""

class BigQueryExecutionError(LGDAError):
    """BigQuery execution errors"""

class TimeoutError(LGDAError):
    """Operation timeout errors"""

# src/error/handlers.py
class ErrorHandler:
    def __init__(self, config: ErrorConfig):
        self.config = config
        self.circuit_breakers = {}

    async def handle_with_recovery(
        self,
        operation: Callable,
        error_types: List[Type[Exception]],
        recovery_strategy: str = "retry"
    ):
        """Handle operation with automatic recovery"""
```

### Error Recovery Strategies

1. **Immediate Recovery** (< 1 second)
   - Retry transient network errors
   - Reparse malformed responses
   - Switch LLM providers on quota errors

2. **Graceful Degradation** (1-10 seconds)
   - Simplify complex queries on execution failure
   - Use cached results when available
   - Fall back to basic analysis on LLM failure

3. **User-Guided Recovery** (> 10 seconds)
   - Ask for query clarification
   - Request simplified analysis
   - Provide alternative approaches

### Implementation Components

1. **Error Classification** (`src/error/classification.py`)
   - Error taxonomy and categorization
   - Severity levels and impact assessment
   - Recovery strategy mapping
   - Error correlation and patterns

2. **Circuit Breakers** (`src/error/circuit_breaker.py`)
   - Provider-specific circuit breakers
   - Automatic fallback mechanisms
   - Health check and recovery
   - State persistence and monitoring

3. **Recovery Engine** (`src/error/recovery.py`)
   - Strategy pattern for recovery approaches
   - Context-aware recovery decisions
   - User experience preservation
   - Performance impact minimization

4. **Error Monitoring** (`src/error/monitoring.py`)
   - Error rate tracking
   - Performance impact measurement
   - Alert thresholds and notifications
   - Error pattern analysis

### Specific Issue Resolutions

#### Hanging Process Prevention
```python
# src/error/timeout.py
class TimeoutManager:
    def __init__(self, default_timeout: int = 300):
        self.default_timeout = default_timeout

    async def with_timeout(self, operation, timeout: Optional[int] = None):
        """Execute operation with guaranteed timeout"""
        timeout = timeout or self.default_timeout

        try:
            return await asyncio.wait_for(operation, timeout=timeout)
        except asyncio.TimeoutError:
            # Force cleanup and raise appropriate error
            await self._force_cleanup(operation)
            raise TimeoutError(
                f"Operation timed out after {timeout}s",
                "OPERATION_TIMEOUT",
                {"timeout": timeout, "operation": str(operation)}
            )
```

#### BigQuery Array Error Handling
```python
# src/error/bigquery_handlers.py
class BigQueryErrorHandler:
    def handle_array_null_error(self, error: Exception, query: str):
        """Handle BigQuery Array null element errors"""
        if "Array cannot have a null element" in str(error):
            # Modify query to handle nulls
            modified_query = self._add_null_handling(query)
            return ErrorRecovery(
                strategy="retry_with_modification",
                modified_input=modified_query,
                message="Added null handling to query"
            )
```

### Dependencies
- **Coordinates with LGDA-007**: Share retry strategy interfaces
- **Uses LGDA-008**: Error configuration management
- **Independent**: Core error handling logic is standalone

## Acceptance Criteria

### Reliability Requirements
- ✅ Zero hanging processes under any error condition
- ✅ Maximum operation timeout of 5 minutes
- ✅ Graceful degradation for all error scenarios
- ✅ Error recovery success rate > 80%

### User Experience Requirements
- ✅ Business-friendly error messages
- ✅ Actionable recovery suggestions
- ✅ Progress indicators during recovery
- ✅ No duplicate or confusing outputs

### Developer Experience Requirements
- ✅ Comprehensive error context and stack traces
- ✅ Error correlation and tracking
- ✅ Performance impact monitoring
- ✅ Alert integration for production issues

### Integration Tests
```python
def test_hanging_process_prevention():
    """Verify no operation can hang indefinitely"""

def test_bigquery_array_error_recovery():
    """BigQuery Array null errors are handled gracefully"""

def test_error_message_user_friendliness():
    """Error messages are appropriate for business users"""

def test_error_recovery_strategies():
    """Different error types trigger appropriate recovery"""

def test_circuit_breaker_functionality():
    """Circuit breakers prevent cascade failures"""
```

## Error Scenarios Coverage

### Network and Timeout Errors
- **LLM Provider timeout**: Auto-retry with exponential backoff
- **BigQuery connection timeout**: Circuit breaker with fallback
- **Network partition**: Cached response or graceful failure

### Data and Query Errors
- **SQL syntax errors**: Auto-fix common patterns
- **BigQuery Array null elements**: Query modification
- **Invalid table references**: Schema validation and correction

### Resource and Quota Errors
- **LLM quota exceeded**: Provider switching
- **BigQuery slot limits**: Query simplification
- **Memory constraints**: Streaming and chunking

### System and Logic Errors
- **Configuration errors**: Validation and defaults
- **State corruption**: State reset and recovery
- **Dependency failures**: Component isolation

## Rollback Plan
1. **Error bypass**: `LGDA_STRICT_ERROR_HANDLING=false`
2. **Component-specific rollback**: Error handler by error handler
3. **Fallback to legacy**: Original error handling paths preserved
4. **Monitoring rollback**: Track error handling performance impact

## Estimated Effort
**3-4 days** | **Files**: ~8 | **Tests**: ~15 new

## Parallel Execution Notes
- **Independent core logic**: Error handling is largely self-contained
- **Coordinates with LGDA-007**: Share retry configuration and interfaces
- **Uses LGDA-008**: Leverage unified configuration for error thresholds
- **Enables monitoring**: Provides foundation for LGDA-011 (observability)
- **Can start immediately**: Core error classes and handlers can be developed independently
