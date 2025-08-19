# SmartKeys Agent Principles (Condensed)

See `LGDA_MEMORANDUM.md` for full context.

1. Modularity
2. Testability
3. Resilience
4. Scalability
5. Observability
6. Integration Simplicity
7. Production Readiness
8. Feynman Principle (Avoid Self-Deception)

Usage Rules:
- Every commit & PR: include SWK-XXX.
- Heuristic modules = pure functions, side effects only in dispatcher layer.
- Privacy first: redact before network, never log raw text unless explicit debug mode.
- Measure before optimizing; if not measured, it “doesn’t exist”.

Checklist (Quick): SRP? Tests? Metrics? Privacy? Undo intact? Assumptions recorded?
