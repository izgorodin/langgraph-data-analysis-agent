# ADR-001: Unified Retry Architecture

**Status**: Proposed
**Date**: 2025-01-20
**Context**: Technical debt resolution following successful NVIDIA LLM + BigQuery integration

## Context and Problem Statement

Current system has conflicting retry mechanisms causing duplicate processing and poor user experience:

1. **Low-level BigQuery retry** (`src/bq.py`): Exponential backoff for infrastructure failures
2. **High-level LangGraph retry** (`src/agent/graph.py`): User-facing workflow retries with max_retries

**Evidence of Problems**:
- User report: "два пустых репорта получили" (received two empty reports)
- Duplicate API calls during error scenarios
- Inconsistent error handling between layers
- Complex debugging when failures occur at both levels

## Decision Drivers

- **User Experience**: Single, predictable retry behavior
- **Resource Efficiency**: Eliminate duplicate API calls
- **Debugging Simplicity**: Clear failure attribution
- **Maintainability**: Single retry logic to maintain

## Considered Options

### Option 1: Remove LangGraph retries, keep only BigQuery retries
**Pros**: Simpler, handles infrastructure failures well
**Cons**: No user-facing retry for LLM failures, poor UX for transient errors

### Option 2: Remove BigQuery retries, keep only LangGraph retries
**Pros**: User-visible retry behavior, better UX
**Cons**: Loss of fine-grained infrastructure error handling

### Option 3: Layered retry with error categorization (CHOSEN)
**Pros**: Best of both worlds - infrastructure resilience + user experience
**Cons**: More complex implementation

## Decision

**Implement layered retry with clear error categorization**:

1. **Infrastructure Layer** (`src/bq.py`): Handle only infrastructure failures
   - Network timeouts
   - Service unavailable (5xx errors)
   - Authentication token refresh
   - NO user-visible retry indicators

2. **Workflow Layer** (`src/agent/graph.py`): Handle business logic failures
   - LLM generation failures
   - SQL validation errors
   - BigQuery quota/permissions issues
   - WITH user-visible progress and retry count

3. **Error Categorization**: Clear distinction between retryable and permanent errors

## Implementation Plan

### Step 1: Categorize BigQuery Errors
```python
# src/bq_errors.py (new file)
@dataclass
class BQErrorCategory:
    is_retryable: bool
    is_infrastructure: bool  # True = silent retry, False = user-visible
    suggested_action: str

BIGQUERY_ERROR_MAPPING = {
    "quotaExceeded": BQErrorCategory(False, False, "Check quota limits"),
    "timeoutExceeded": BQErrorCategory(True, True, "Query complexity too high"),
    "accessDenied": BQErrorCategory(False, False, "Check permissions"),
    # ... complete mapping
}
```

### Step 2: Update BigQuery Client
```python
# src/bq.py - Infrastructure retry only
def execute_query_with_retry(sql: str) -> pd.DataFrame:
    for attempt in range(max_infrastructure_retries):
        try:
            return _execute_query(sql)
        except Exception as e:
            error_cat = categorize_bq_error(e)
            if not error_cat.is_infrastructure or not error_cat.is_retryable:
                raise  # Let workflow layer handle
            # Silent infrastructure retry
            time.sleep(exponential_backoff(attempt))
    raise  # Final failure
```

### Step 3: Update LangGraph Retry Logic
```python
# src/agent/graph.py - User-facing retry only
def should_retry_from_execute(state: AgentState) -> bool:
    """Only retry business logic failures, not infrastructure failures"""
    if not state.last_error:
        return False

    error_cat = categorize_error(state.last_error)
    return (
        state.retry_count < state.max_retries and
        error_cat.is_retryable and
        not error_cat.is_infrastructure
    )
```

### Step 4: Enhanced Error Context
```python
# src/agent/nodes.py - Clear error attribution
def execute_sql_node(state: AgentState) -> AgentState:
    try:
        state.df = execute_query_with_retry(state.sql)
        return state
    except InfrastructureError as e:
        # Infrastructure exhausted retries
        return _set_validation_error(state, f"BigQuery service issue: {e}")
    except BusinessLogicError as e:
        # User-facing error with retry possibility
        return _set_validation_error(state, f"Query issue: {e}")
```

## Expected Benefits

### User Experience
- Clear progress indicators during retries
- No surprise duplicate reports
- Actionable error messages with retry context

### Technical Benefits
- Eliminate duplicate API calls
- Clear separation of concerns
- Simplified debugging and monitoring

### Maintenance
- Single source of retry configuration
- Consistent error handling patterns
- Easier testing of retry scenarios

## Consequences

### Positive
- Improved user experience with predictable retry behavior
- Resource efficiency through elimination of duplicate calls
- Clearer error attribution and debugging

### Negative
- Increased complexity in error categorization
- Need to maintain error mapping as BigQuery API evolves
- More sophisticated testing required

### Migration Impact
- Low risk: Changes are internal to retry logic
- Backward compatible: External interfaces unchanged
- Rollback plan: Keep current retry flags for gradual migration

## Validation Plan

### Unit Tests
- [ ] Error categorization logic
- [ ] Infrastructure vs business logic retry separation
- [ ] Retry count limits and backoff behavior

### Integration Tests
- [ ] End-to-end retry scenarios with controlled failures
- [ ] User-visible progress during workflow retries
- [ ] Silent infrastructure retries with no user impact

### Production Validation
- [ ] Monitor for duplicate API calls (should be zero)
- [ ] User feedback on retry experience
- [ ] Error attribution clarity in logs

## Related ADRs
- ADR-002: Configuration Management (retry limits and timeouts)
- ADR-004: CLI Error Handling (progress indicators and error display)

---
*This ADR addresses the most critical technical debt identified in the architecture analysis.*
