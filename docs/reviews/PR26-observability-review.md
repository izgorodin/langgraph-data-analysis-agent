# PR #26 — LGDA-011 Observability: Review Notes

Status: Draft review based on local checkout and test runs (branch pr-26).

Summary
- Adds src/observability/* for logging, metrics, tracing, health, business metrics; manager and integration points.
- Extends config with observability settings and helpers.
- Adds unit tests for observability components.

Build & tests (local)
- make test produced 8 failures, 403 passed, 1 skipped.
- Notable failures touching CLI/Graph (likely not specific to observability but exist on this branch):
  - CLI integration: long output truncation, state streaming, state model_dump handling.
  - LangGraph integration: GraphRecursionError and StopIteration from error path and end conditions.
  - LLM model default tokens mismatch (4000 vs 1000).
  - ConfigFactory managers isinstance assert False.

Findings
- Logging: uses datetime.utcnow which is deprecated — swap to datetime.now(datetime.UTC).
- Manager initialization emits many DeprecationWarnings for legacy env; expected but noisy. Consider warning once per var using a memo or filter.
- Coverage: observability files mixed coverage; instrumented_nodes.py 0% indicates it’s not wired into tests yet; health and tracing have large untested areas.
- No regression guard for CLI/graph behavior — failures indicate non-observability changes present in this branch.

Required changes
1) Replace datetime.utcnow() with timezone-aware variant in src/observability/logging.py.
2) Reduce duplicate deprecation warnings in manager by guarding mapping once per process.
3) CLI fixes:
   - cli.py prints Agent Report panel twice; remove duplicate print.
   - Ensure verbose streaming code handles dict vs pydantic objects and truncates extremely long JSON deterministically; tests expect successful exit, not specific content.
4) Graph fixes:
   - build_graph.validate_sql conditional path can loop between synthesize_sql and validate_sql without a stop when llm outputs invalid SQL repeatedly. Add retry guard: when retry_count exceeds max, break to END and keep error, and ensure state.error cleared only when moving forward.
   - Ensure on_valid returns END under error and no retries left; current code does, but StopIteration suggests node function may raise. Wrap node calls or ensure nodes return state consistently.
5) LLM models:
   - Align LLMRequest default max_tokens with tests (1000) or update tests/docs.
6) ConfigFactory isinstance failure:
   - Re-check imports; make sure only a single CredentialManager class exists.

Nice-to-have
- Add smoke tests for instrumented_nodes to lift coverage from 0% and validate it’s non-invasive when observability disabled.
- Add health checks lightweight tests with a fake dependency.

Approval criteria
- All current failures resolved on pr-26.
- No new lint errors.
- Observability unit tests remain green; coverage for observability >60% overall; no critical hot paths untested.

Next actions
- Implement quick fixes in cli.py (duplicate print, robust streaming handling).
- Implement datetime.utcnow replacement.
- Evaluate graph retry/end handling per failing tests and patch accordingly.
- Re-run tests.
