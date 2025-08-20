# Architecture Analysis & Technical Debt Resolution Plan
*Generated: January 20, 2025*

## Executive Summary

Following successful real-world validation with NVIDIA LLM and BigQuery integration, comprehensive architectural analysis revealed critical technical debt requiring systematic resolution before production deployment.

**Current Status**: ✅ Working MVP with production-grade features
**Primary Concern**: 🚨 Scattered architecture patterns creating maintenance and reliability risks
**Recommended Action**: 📋 Systematic technical debt cleanup with ADR-driven approach

## Critical Issues Identified

### 1. Dual Retry Logic Systems 🔴 HIGH PRIORITY

**Problem**: Conflicting retry implementations causing duplicate processing
- `src/bq.py`: Low-level BigQuery retry with exponential backoff
- `src/agent/graph.py`: High-level LangGraph retry with max_retries counter

**Evidence**:
- User report: "два пустых репорта получили" (received two empty reports)
- Double processing in error scenarios
- Inconsistent error handling between layers

**Impact**:
- User experience degradation
- Resource waste (double API calls)
- Debugging complexity

**Resolution Strategy**:
1. Create ADR-001: Unified Retry Architecture
2. Consolidate to single retry layer (prefer LangGraph level)
3. Remove low-level retries for user-facing operations
4. Preserve BigQuery retries only for infrastructure failures

### 2. Hardcoded Values Proliferation 🔴 HIGH PRIORITY

**Problem**: Configuration values scattered across multiple files
- Token limits: `src/config.py`, `src/llm/compat.py`, `src/llm/models.py`
- Model names: CLI, config, compatibility layer
- SQL templates: hardcoded in nodes, prompts, and tests

**Evidence**:
```python
# Multiple token definitions
src/config.py:       llm_max_tokens: int = 4000
src/llm/compat.py:   max_tokens=4000
src/llm/models.py:   max_tokens: int = 4000
```

**Impact**:
- Configuration drift
- Maintenance overhead
- Testing inconsistencies

**Resolution Strategy**:
1. Create ADR-002: Configuration Management Patterns
2. Implement single source of truth for all configurable values
3. Remove hardcoded values from business logic
4. Centralize configuration validation

### 3. Test Logic Divergence 🟡 MEDIUM PRIORITY

**Problem**: Test implementations diverging from main code paths
- Test-specific retry logic not matching production
- Mock behavior inconsistent with real provider behavior
- Configuration override patterns different between test and main

**Evidence**:
- `tests/unit/test_bq_hardening.py`: Complex test-only retry simulation
- CLI parameter propagation working in main but not tested
- Provider selection logic tested differently than implemented

**Impact**:
- False confidence in test coverage
- Production bugs not caught by tests
- Maintenance burden for dual implementations

**Resolution Strategy**:
1. Create ADR-003: Test-Production Parity
2. Align test mocks with actual provider behavior
3. Test actual configuration flows, not mock implementations
4. Implement integration test suite with real (but controlled) providers

### 4. CLI Error Handling 🟡 MEDIUM PRIORITY

**Problem**: Inconsistent error display and reporting
- Duplicate report display in error scenarios
- Silent failures without proper error propagation
- Missing progress indicators for long-running operations

**Evidence**:
- User report: "то-то мы повисли! и ошибки даже не выкинули"
- BigQuery ARRAY_AGG errors not surfaced to user
- No visual feedback during query execution

**Impact**:
- Poor user experience
- Difficult debugging
- Production deployment risks

**Resolution Strategy**:
1. Create ADR-004: CLI Error Handling Standards
2. Implement consistent error reporting patterns
3. Add progress indicators for all long-running operations
4. Surface all relevant errors to user with actionable context

## Architecture Decision Records (ADRs) Required

### ADR-001: Unified Retry Architecture
**Decision**: Consolidate retry logic to LangGraph layer with BigQuery-specific fallbacks
**Rationale**: User-facing retries should be coordinated at workflow level
**Implementation**: Remove graph-level retries, enhance node-level error handling

### ADR-002: Configuration Management Patterns
**Decision**: Single configuration source with typed validation
**Rationale**: Prevent configuration drift and improve maintainability
**Implementation**: Pydantic-based config with environment precedence rules

### ADR-003: Test-Production Parity
**Decision**: Tests must use same code paths as production
**Rationale**: Increase confidence in test coverage
**Implementation**: Integration tests with controlled provider responses

### ADR-004: CLI Error Handling Standards
**Decision**: Consistent error formatting with actionable guidance
**Rationale**: Improve user experience and debugging
**Implementation**: Rich-based error display with retry suggestions

### ADR-005: Provider Interface Standardization
**Decision**: Uniform provider interface with standardized error handling
**Rationale**: Simplify provider swapping and testing
**Implementation**: Abstract base class with required error mapping

## Implementation Roadmap

### Phase 1: Critical Infrastructure (Week 1)
- [ ] **ADR-001**: Consolidate retry logic
  - Remove duplicate retry in graph.py conditional edges
  - Enhance bq.py error categorization (transient vs permanent)
  - Update error handling in nodes.py
- [ ] **ADR-002**: Centralize configuration
  - Move all config values to single source
  - Remove hardcoded tokens from compat.py and models.py
  - Add configuration validation tests

### Phase 2: Testing Alignment (Week 2)
- [ ] **ADR-003**: Test-production parity
  - Refactor test_bq_hardening.py to use actual configuration flows
  - Create integration test suite with controlled providers
  - Add CLI parameter propagation tests
- [ ] **ADR-004**: CLI improvements
  - Implement progress indicators using Rich progress bars
  - Standardize error display formatting
  - Add retry suggestions in error messages

### Phase 3: Provider Standardization (Week 3)
- [ ] **ADR-005**: Provider interfaces
  - Create abstract provider base class
  - Standardize error mapping across providers
  - Implement provider health checks
- [ ] **Documentation**: Update architecture diagrams
- [ ] **Validation**: End-to-end testing with all provider combinations

## Success Metrics

### Technical Metrics
- [ ] Zero duplicate retry executions in error scenarios
- [ ] 100% configuration values sourced from single location
- [ ] Test coverage matches production code paths
- [ ] All long-running operations show progress indicators

### User Experience Metrics
- [ ] Clear error messages with actionable next steps
- [ ] No silent failures or hanging processes
- [ ] Consistent behavior across all provider combinations
- [ ] Zero configuration-related production issues

## Risk Mitigation

### Implementation Risks
- **Breaking Changes**: Each ADR implementation should be backward compatible
- **Provider Disruption**: Maintain current provider contracts during refactoring
- **Test Disruption**: Incremental test updates to avoid coverage gaps

### Mitigation Strategies
- Feature flags for new retry logic during transition
- Comprehensive integration testing before each phase
- Rollback plans for each ADR implementation
- Continuous validation against working commit 17704bd

## Current Working State (Preserved)

**Commit**: `17704bd` - MILESTONE: Working NVIDIA LLM + BigQuery integration
**Validated Features**:
- ✅ NVIDIA provider with 4000 tokens
- ✅ Complex query analytics (AOV by segments)
- ✅ BigQuery authentication and execution
- ✅ Schema-aware SQL generation
- ✅ Security validation and injection protection

**Known Working Queries**:
```
Simple: "Count orders in 2023" → 21,133 orders
Complex: "What is the average order value and its distribution across key customer segments?"
→ Poland: $392, Japan: $180.7, detailed executive insights
```

This analysis provides foundation for systematic technical debt resolution while preserving all current working functionality.
