# LangGraph Data Analysis Agent - Development Principles

Adapted from SmartKeys Agent Principles for our BigQuery analysis project.

## Core 8 Principles (Adapted for Data Analysis Agent)

1. **Modularity** – Separate LLM calls, SQL validation, BigQuery client, data analysis, reporting. No cross-layer coupling.
2. **Testability** – SQL validation + data analysis must be unit testable without GCP APIs. LLM calls mocked.
3. **Resilience** – Failure in LLM or BigQuery never crashes agent; fallback to deterministic responses.
4. **Scalability** – Query cost per request ~O(1); result sets capped; no memory leaks.
5. **Observability** – Every query attempt emits structured log. Latency and cost tracked.
6. **Integration Simplicity** – Clean CLI interface; explicit naming (no "AgentManager").
7. **Production Readiness** – Proper error handling, cost limits, security validation.
8. **Feynman Principle** – Track assumptions (SQL correctness, schema accuracy) → validate with tests.

## Behavioral Rules for Development

- Reference a LGDA-XXX ID in each commit/PR
- Never introduce LLM call without cost/error guard
- If SQL validation fails → fallback to error message, never execute unsafe SQL
- Test-first approach: write test, make it fail, implement, make it pass
- When adding config: define default, document in README, add to .env.example

## Component Contracts (TDD)

| Component | Inputs | Outputs | Errors | Test Strategy |
|-----------|--------|---------|--------|---------------|
| SQLValidator | raw SQL string | validated SQL or error | parse/policy errors | Unit tests with sqlglot |
| SchemaFetcher | table names | schema dict | BQ connection errors | Mock BQ responses |
| QueryExecutor | validated SQL | DataFrame | BQ errors, limits | Dry-run + mocked results |
| DataAnalyzer | DataFrame | summary dict | analysis errors | Synthetic DataFrames |
| ReportGenerator | summary + question | insight text | LLM errors | Mock LLM responses |
| MemoryManager | interactions | chat history | storage errors | In-memory store |

## TDD Decision Checklist

- [ ] LGDA-XXX ID referenced?
- [ ] Test written before implementation?
- [ ] Core logic isolated from external dependencies?
- [ ] Observability/logging added?
- [ ] Cost/security impact evaluated?
- [ ] Error handling tested?

## Anti-Patterns

- Mixing LLM calls with SQL validation logic
- Direct BigQuery calls in business logic without abstraction
- Logging sensitive data without redaction
- Silent failures in query execution
- Untested error paths

## Fast Failure Guidelines

If a new component increases query latency > +2s or cost > $0.01 per query: revert or gate behind feature flag.

## Assumption Log

```
ASSUMPTION: sqlglot correctly parses 99% of generated BigQuery SQL (validate with corpus in LGDA-001)
ASSUMPTION: Schema cache valid for 1 hour (extend if schema changes detected in LGDA-002)
ASSUMPTION: MAX_BYTES_BILLED=100MB sufficient for 95% of queries (monitor in LGDA-003)
```

## Testing Strategy

- **Unit Tests**: SQL validation, data analysis, report formatting
- **Integration Tests**: Schema fetching, query execution (with dry-run)
- **E2E Tests**: CLI flow with mocked LLM/BQ responses
- **Performance Tests**: Query latency, cost tracking
