# Copilot Instructions (LGDA - LangGraph Data Analysis Agent)

Purpose: Guide AI assistants (GitHub Copilot, etc.) to produce consistent, safe, production‑aligned code for LangGraph Data Analysis Agent.

## Repository Focus
LGDA: Production-ready data analysis agent using LangGraph + BigQuery + Gemini/Bedrock LLMs. Focus on security, performance, and TDD approach with comprehensive testing strategy.

## Core Architecture Principles
1. **Node-based LangGraph Flow**: plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report
2. **Security-First**: SQL injection prevention, table whitelisting, credential protection
3. **Multi-LLM Strategy**: Gemini primary + Bedrock fallback with intelligent switching
4. **TDD Approach**: Test-driven development with 80%+ coverage requirements
5. **Production Ready**: Robust error handling, monitoring, configuration management

## Required Behavior
- Always reference a task ID (LGDA-XXX) in commit messages & PR bodies
- Follow ADR decisions documented in docs/adr/ directory
- Implement comprehensive security for SQL validation (per ADR 003)
- Use unified LLM interface with provider abstraction
- Maintain separation between core logic and external dependencies
- Provide comprehensive test coverage for all critical paths

## When Adding Code
Checklist before proposing changes:
- [ ] Which LGDA task does this belong to?
- [ ] Security implications reviewed (SQL injection, credential exposure)?
- [ ] Performance impact assessed (< 2s for simple queries)?
- [ ] Error handling comprehensive with proper fallbacks?
- [ ] Tests written first (TDD approach)?
- [ ] ADR compliance verified?

## File Structure Conventions
- `src/config.py` - Configuration management and credential handling
- `src/bq.py` - BigQuery client with connection pooling
- `src/llm.py` - LLM provider abstraction and fallback logic
- `src/agent/` - LangGraph nodes and workflow definition
- `tests/unit/` - Unit tests with comprehensive mocking
- `tests/integration/` - Integration tests with real services
- `docs/adr/` - Architecture Decision Records
- `tasks/` - Detailed task specifications

## Security & Privacy Rules (Critical)
- **SQL Injection Prevention**: All SQL must pass through validation (LGDA-002)
- **Credential Management**: Never log credentials, use proper masking
- **Table Whitelisting**: Only allow access to approved tables per ADR 003
- **LLM Security**: Sanitize inputs, validate outputs, prevent prompt injection
- **Environment Isolation**: Separate dev/staging/production configurations

## Performance Requirements
- Simple queries (< 1000 rows): < 2 seconds end-to-end
- Complex aggregations: < 30 seconds
- SQL validation: < 100ms p95
- LLM response: < 3 seconds p95
- Memory usage: < 512MB for typical workloads

## Testing Strategy (TDD)
- Write tests BEFORE implementation
- Unit tests: Mock all external dependencies (BigQuery, LLMs)
- Integration tests: Real service calls with test credentials
- Minimum 80% code coverage required
- Security tests: SQL injection, credential leakage, error handling

## LLM Integration Guidelines
- Use provider abstraction layer (src/llm.py)
- Implement circuit breaker for failures
- Cost tracking and budget limits
- Response validation and quality scoring
- Graceful degradation on provider failures

## Common Anti‑Patterns to Block
- Direct SQL concatenation (use parameterized queries)
- Hardcoded credentials in source code
- Missing error handling in external service calls
- Synchronous blocking calls in critical paths
- Unbounded result sets from BigQuery
- Missing input validation for user queries

## Configuration Management
- Environment-based configuration (dev/staging/production)
- Secure credential storage and rotation
- Feature flags for gradual rollouts
- Performance tuning per environment
- Comprehensive validation of all settings

## Monitoring & Observability
- Structured logging with correlation IDs
- Performance metrics collection
- Error tracking and alerting
- Cost monitoring for BigQuery and LLMs
- Security audit logging

## Code Quality Standards
- Type hints required for all functions
- Comprehensive docstrings for public APIs
- Black formatting and isort imports
- Mypy type checking passing
- Flake8 linting compliance

## Escalation Protocol
If Copilot detects:
- Potential security vulnerability → Add TODO with SECURITY tag
- Performance concern → Add TODO with PERFORMANCE tag
- Missing test coverage → Add TODO with TESTING tag
- ADR violation → Add TODO with ADR-XXX reference

## Integration with GitHub Automation
- CI pipeline validates all code quality standards
- Auto-generation of issues from task files
- Automatic labeling based on component areas
- Security scanning on every commit
- Performance regression detection

---
Update this file via PR with LGDA-XXX task reference. Keep focused on production readiness and security.
