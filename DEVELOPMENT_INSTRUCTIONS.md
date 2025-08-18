# Development Instructions for LangGraph Data Analysis Agent

## My Role & Approach

I am implementing a production-ready data analysis agent using **Test-Driven Development (TDD)** approach, following adapted SmartKeys principles.

## TDD Workflow

1. **Red** → Write failing test first
2. **Green** → Implement minimal code to pass test  
3. **Refactor** → Clean up while keeping tests green
4. **Repeat** → Next feature/requirement

## Task Execution Order

### Phase 1: Core Testing Infrastructure (LGDA-001 to LGDA-005)
1. **LGDA-001**: Test fixtures and mocks setup
2. **LGDA-002**: SQL validation with sqlglot (unit tests)
3. **LGDA-003**: Schema fetching with mocked BigQuery
4. **LGDA-004**: Data analysis with synthetic DataFrames
5. **LGDA-005**: Basic CLI testing framework

### Phase 2: Business Logic (LGDA-006 to LGDA-010)
6. **LGDA-006**: LangGraph node implementations (mocked LLM)
7. **LGDA-007**: Memory management and chat history
8. **LGDA-008**: Error handling and fallbacks
9. **LGDA-009**: Cost and performance monitoring
10. **LGDA-010**: Integration tests with dry-run

### Phase 3: Production Features (LGDA-011 to LGDA-015)
11. **LGDA-011**: Real LLM integration with retry logic
12. **LGDA-012**: BigQuery integration with security policies
13. **LGDA-013**: CLI polish and verbose logging
14. **LGDA-014**: End-to-end smoke tests
15. **LGDA-015**: Performance benchmarks and optimization

## Implementation Rules

### Before Writing Any Code:
1. Create/update task spec with LGDA-XXX ID
2. Write test that describes expected behavior
3. Run test → confirm it fails (Red)
4. Implement minimal solution → make test pass (Green)  
5. Refactor for clarity → keep tests green
6. Commit with LGDA-XXX reference

### File Organization:
```
tests/
├── unit/
│   ├── test_sql_validator.py
│   ├── test_schema_fetcher.py
│   ├── test_data_analyzer.py
│   └── test_report_generator.py
├── integration/
│   ├── test_bigquery_client.py
│   └── test_langgraph_flow.py
├── fixtures/
│   ├── sample_schemas.json
│   ├── sample_dataframes.pkl
│   └── sample_responses.json
└── conftest.py
```

### Testing Priorities:
1. **Happy path** - core functionality works
2. **Error cases** - graceful failure handling
3. **Edge cases** - boundary conditions
4. **Performance** - latency and cost limits

### Mock Strategy:
- Mock external dependencies (BigQuery, Gemini API)
- Use real data structures internally (pandas DataFrames, JSON)
- Test business logic in isolation
- Integration tests use dry-run mode where possible

### Observability Requirements:
- Log structured data (JSON) for each major operation
- Track timing for LLM calls, SQL execution, data analysis
- Monitor costs (BigQuery bytes processed, LLM tokens)
- Export metrics for production monitoring

## Quality Gates

### Before Merge:
- [ ] All tests pass
- [ ] Test coverage > 80% for new code
- [ ] No hardcoded secrets or credentials
- [ ] Error handling tested
- [ ] Performance within limits (< 2s query, < $0.01 cost)
- [ ] LGDA-XXX task referenced in commit

### Code Review Checklist:
- [ ] Single Responsibility Principle followed
- [ ] Dependencies properly abstracted
- [ ] Error messages user-friendly
- [ ] No silent failures
- [ ] Logging appropriate (not too verbose, not too silent)

## Tools I Need

### Testing Tools:
- pytest (Python testing framework)
- pytest-mock (for mocking dependencies)
- pytest-cov (coverage reporting)
- pandas testing utilities
- sqlglot parsing validation

### Development Tools:
- Black/Ruff (code formatting)
- mypy (type checking)
- pre-commit hooks
- Makefile for common tasks

### Monitoring Tools:
- structlog (structured logging)
- time/cost tracking utilities
- simple metrics collection

Let me start with LGDA-001: setting up the testing infrastructure.
