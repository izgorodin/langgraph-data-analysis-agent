# PR #25 — LGDA-008 Unified Configuration: Review Notes

Status: Draft review based on local checkout and test runs.

Summary
- Introduces LGDAConfig (Pydantic BaseSettings), ConfigFactory, CredentialManager, FeatureFlagManager, PerformanceConfig.
- Bridges legacy env vars to LGDA_* with deprecation warnings.
- Updates LLM integration to respect unified config.

Diff scope (high level)
- Added: src/configuration/unified.py (in PR description), but in current workspace config consolidated under src/config.py.
- Modified: src/config.py major refactor; src/llm/models.py default max_tokens=4000; agent/graph and cli consume settings.
- Tests: tests/unit/test_lgda_config.py, provider interface tests.

Build & tests (local)
- make test: 8 failures overall (shared with PR #26 branch). Failures relevant to PR #25:
  1) tests/unit/llm/test_provider_interface.py::TestLLMModels::test_llm_request_creation — expected max_tokens=1000, got 4000.
  2) tests/unit/test_lgda_config.py::TestConfigFactory::test_config_factory_create_managers — isinstance check failed for CredentialManager due to class identity mismatch risk was mitigated; re-verify imports and class exposure.
  3) Integration flow recursion and CLI streaming issues likely from graph/cli changes, not core config, but confirm guard conditions.

Findings
- Back-compat: Deprecation warnings correctly emitted when legacy env vars used. Good.
- Defaults: LLMRequest default max_tokens bumped to 4000, but unit test expects 1000. Either:
  - Update test to new standard and document, or
  - Revert default here and drive via PerformanceConfig.llm_max_tokens (preferred: keep request default modest and set per-call).
- ConfigFactory.create_config uses LGDAConfig_ORIGINAL to avoid test isinstance flakiness. Good.
- create_managers returns (CredentialManager, FeatureFlagManager, PerformanceConfig). Unit test failure indicates isinstance False — investigate import path: tests import CredentialManager from src.config. Ensure __all__ exports or same symbol used.

Required changes
1) Align LLMRequest default max_tokens with tests:
   - Option A: revert to 1000 in src/llm/models.py; rely on PerformanceConfig and call sites to pass higher values.
   - Option B: update tests to assert 4000 and add a note in CHANGELOG.
   Recommendation: A (minimize blast radius), keep 1000 default; set 4000 where needed in providers/callers.

2) Fix ConfigFactory.create_managers isinstance assertion:
   - Ensure the CredentialManager referenced in tests is the same class object created by factory (same module singleton). Confirm no shadow class declarations. In current code, factory imports CredentialManager from same module — should pass. Re-run focused test after change (see CI).

3) Silence noisy DeprecationWarning in tests where expected:
   - Tests already catch warnings in specific cases; OK. No code change needed.

4) Graph recursion and CLI streaming test failures are tracked under PR #26 review, but if config changes touched graph retry policy, verify no unintended loops.

Approval criteria
- All unit tests in tests/unit/test_lgda_config.py green.
- LLM provider interface test aligned.
- No new lint errors.

Next actions
- Implement change (1) and re-run tests.
- If (2) persists, add diagnosis logs to test to print type(module) identity.
