# LGDA-016: Error Propagation After Retries

## Summary
Investigate and fix error propagation issue in LangGraph where errors are not properly tracked in final state after all retries are exhausted.

## Background
During implementation of unified retry architecture (LGDA-007), an integration test revealed that errors are not properly propagated to final state when all retries are exhausted. The test `test_graph_end_conditions` fails because `final_state.error` is `None` when it should contain the error message.

## Problem Description
When a validation error occurs and retry limit is reached (`retry_count >= max_retries`), the graph should terminate with error state preserved. However, the error is lost during graph execution flow.

## Investigation Summary
### What We Tried:
1. **Debug output analysis**: Added debug prints showing `final_state.error=None` despite initial error being set
2. **Retry count adjustment**: Set `retry_count = max_retries` to avoid retry loops - didn't help
3. **Error handler logic**: Added error restoration from `last_error` in `error_handler_node` - this was a "patch" solution, not addressing root cause
4. **Test restructuring**: Created two scenarios (error after retries vs success after retry) to clarify expected behavior

### Current Understanding:
- Error starts as `"Validation failed"` in test state
- Graph transitions through retry logic in `on_valid()` function
- When `retry_count >= max_retries`, graph goes to `error_handler` node
- By the time we reach `error_handler`, both `error` and `last_error` are `None`
- Final state has complete execution results (SQL, report, etc.) but no error

### Key Code Locations:
- `src/agent/graph.py`: `on_valid()` function handles retry logic
- `src/agent/nodes.py`: `error_handler_node()` for final error processing
- `tests/integration/test_langgraph_flow.py`: Failing test case

## Root Cause Hypothesis
The error is being cleared somewhere in the graph execution flow, possibly:
1. During state transitions between nodes
2. In the mock setup (`validate_sql_node` mock behavior)
3. In the graph wrapper (`_AppWrapper.invoke()` method)
4. In the conditional edge logic that decides graph flow

## Requirements
### Must Have:
- Error state preservation when retry limit is exhausted
- Clean separation between "error fixed by retry" vs "error persists after all retries"
- No artificial error restoration (avoid "patches")

### Should Have:
- Clear traceability of error state through graph execution
- Consistent behavior between mocked and real graph execution
- Proper test coverage for both success and failure scenarios

### Could Have:
- Enhanced debugging/logging for error state transitions
- Documentation of error handling architecture

## ADR (Architecture Decision Record)
### Decision: Investigate error state management in LangGraph flow
- **Context**: Unified retry architecture needs reliable error propagation
- **Decision**: Fix root cause of error loss, not symptoms
- **Consequences**: May require refactoring graph logic or state management

## Performance Considerations
- Error tracking should not impact normal execution performance
- State copying/mutation should be minimal

## Security Considerations
- Error messages should not leak sensitive information
- Error state should be properly sanitized before final return

## Integration Impact
- Integration tests must properly validate error scenarios
- Mock behavior should accurately reflect real node behavior
- Graph execution flow must be predictable and testable

## Implementation Difficulty: Medium
**Reasoning**: Requires deep understanding of LangGraph state management and careful debugging of execution flow.

## Test Strategy
1. **Preserve failing test**: Keep current test as regression detector
2. **Add tracing**: Insert state logging at key transition points
3. **Mock analysis**: Verify mock behavior matches expected state transitions
4. **End-to-end testing**: Test with real nodes (not just mocks)

## Definition of Done
- [ ] Error properly preserved when retry limit exhausted
- [ ] Test `test_graph_end_conditions` passes without artificial patches
- [ ] Both success and failure retry scenarios work correctly
- [ ] Root cause identified and documented
- [ ] No regression in existing functionality

## Notes
- Test intentionally left failing to track this architectural debt
- Do not use "last_error restoration" patches - find real root cause
- This is critical for production error handling reliability

## Related Tasks
- LGDA-007: Unified retry architecture (parent task)
- Future: Error logging and monitoring enhancements
