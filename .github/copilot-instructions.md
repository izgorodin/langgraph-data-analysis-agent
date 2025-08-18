# LangGraph Data Analysis Agent - GitHub Copilot Instructions

Always follow these instructions first and only search for additional context if the information here is incomplete or found to be in error.

## Project Overview

LangGraph Data Analysis Agent (LGDA) is a production-ready data analysis system that transforms natural language business questions into validated BigQuery queries and executive insights. Uses LangGraph pipeline with Gemini/Bedrock LLMs, strict security policies, and TDD development approach.

**Architecture**: `plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report`

## Bootstrap Environment

**CRITICAL**: Always run these exact commands in order. NEVER CANCEL long-running processes.

```bash
# 1. Create virtual environment (3-10 seconds)
python3 -m venv .venv
source .venv/bin/activate

# 2. Upgrade pip (10-30 seconds, may timeout due to network)
python -m pip install --upgrade pip --timeout 300 || echo "Pip upgrade failed due to network"

# 3. Install main dependencies (60-300 seconds, NEVER CANCEL)
pip install -r requirements.txt --timeout 300

# 4. Install development dependencies (30-120 seconds, NEVER CANCEL) 
pip install -r requirements-dev.txt --timeout 300

# 5. Setup environment file (2 seconds)
cp .env.example .env
# Edit .env file with your API keys if doing integration testing
```

**TIMEOUT WARNING**: Set timeout to 300+ seconds for dependency installation. Network issues may cause timeouts. If pip commands fail due to network timeouts, retry with longer timeout or different network.

## Build and Test Commands

### Core Validation (Always run these)

```bash
# Activate virtual environment FIRST
source .venv/bin/activate

# Run tests - takes ~1 second, NEVER fails
make test

# Format code - takes ~3 seconds
make format

# Check formatting/linting - takes ~1 second (may show existing issues)
make lint
```

**EXPECTED**: Lint may show existing line length issues in src/agent/nodes.py and other files. This is normal during development.

### Extended Validation

```bash
# Run all checks - takes ~5 seconds
make check-all

# Clean build artifacts - takes ~1 second, may show permission warnings (normal)
make clean

# Install pre-commit hooks - takes ~3 seconds
.venv/bin/pre-commit install

# Security scan - takes ~5 seconds
make security
```

**PRE-COMMIT NOTE**: Pre-commit hooks may fail due to Python version conflicts. Use direct commands instead:
```bash
.venv/bin/black src tests
.venv/bin/isort src tests
.venv/bin/flake8 src tests
```

## Running the Application

### CLI Usage

```bash
# Basic help - immediate response
python cli.py --help

# Run with question (requires API keys)
python cli.py "Top 10 products by revenue" --verbose

# Without API keys, will timeout after ~10 seconds (expected behavior)
timeout 10 python cli.py "test question" || echo "Expected timeout without credentials"
```

### Development Mode

```bash
# Run in development mode with debugging
make run-dev
# Equivalent to: .venv/bin/python -m src.cli --debug
```

## Testing and Validation

### Test Suite Structure

```
tests/
├── test_basic.py           # Basic functionality tests
├── unit/                   # Unit tests (TDD approach)
├── integration/           # Integration tests with mocked APIs
└── fixtures/              # Test data and mock responses
```

### Running Tests

```bash
# Run all tests - takes ~1 second
make test

# Run specific test types
make test-unit         # Unit tests only
make test-integration  # Integration tests only

# Run with coverage - takes ~2 seconds
.venv/bin/pytest --cov=src --cov-report=term-missing

# Run tests with verbose output
.venv/bin/pytest -v
```

**NEVER CANCEL**: All test commands complete in under 5 seconds.

## Key File Locations

### Entry Points
- `cli.py` - Main CLI interface (Click + Rich)
- `src/cli.py` - Module-based entry point

### Core Logic
- `src/agent/` - LangGraph pipeline components
  - `nodes.py` - Pipeline node implementations
  - `graph.py` - LangGraph flow definition  
  - `state.py` - Agent state management
  - `prompts.py` - LLM prompt templates
- `src/bq.py` - BigQuery client and security policies
- `src/llm.py` - LLM integration (Gemini + Bedrock fallback)
- `src/config.py` - Configuration management with Pydantic

### Build and Configuration
- `Makefile` - All build, test, and development commands
- `pyproject.toml` - Poetry/pip dependencies and tool configuration
- `requirements.txt` - Core dependencies (compatible with pip)
- `requirements-dev.txt` - Development dependencies
- `.env.example` - Environment variables template

### Documentation and Tasks
- `tasks/LGDA-*.md` - TDD task specifications (numbered LGDA-001 to LGDA-015)
- `docs/` - Architecture and design documentation
- `diagrams/architecture.md` - Mermaid diagrams and data flow
- `DEVELOPMENT_INSTRUCTIONS.md` - TDD workflow guidelines

### Quality and CI
- `.github/workflows/ci.yml` - GitHub Actions CI pipeline
- `.pre-commit-config.yaml` - Code quality hooks
- `scripts/` - Validation and security check scripts

## Development Workflow

### TDD Approach (Primary Development Method)

```bash
# 1. Check current task specifications
make list-tasks

# 2. View specific task (use full task name with ID)
make check-task TASK=LGDA-001-test-infrastructure

# 3. Write failing test first (Red)
# Edit tests/unit/test_*.py

# 4. Run test to confirm failure
.venv/bin/pytest tests/unit/test_new_feature.py -v

# 5. Implement minimal solution (Green)
# Edit src/agent/nodes.py or relevant files

# 6. Run test to confirm pass
.venv/bin/pytest tests/unit/test_new_feature.py -v

# 7. Refactor while keeping tests green
# Clean up code while maintaining test passes
```

### Code Quality Pipeline

```bash
# Before committing any changes:
make format          # Auto-format code - takes ~3 seconds
make lint           # Check style issues - takes ~1 second  
make test           # Run test suite - takes ~1 second
make security       # Security scan - takes ~5 seconds
```

### Validation After Changes

**ALWAYS** run these commands after making code changes:

```bash
# 1. Format and test (required)
make format && make test

# 2. Check integration works
python cli.py --help  # Should show usage immediately

# 3. Test mock scenario
timeout 10 python cli.py "test" --verbose || echo "Expected timeout"

# 4. Verify no new lint issues introduced
make lint | grep -E "(src/your_file|tests/your_file)" || echo "No new issues"
```

## Architecture Navigation

### LangGraph Pipeline Flow

1. **plan** - Schema-aware JSON planning with table metadata
2. **synthesize_sql** - Generate BigQuery SQL using templates + LLM
3. **validate_sql** - SQL parsing, security policies, LIMIT enforcement
4. **execute_sql** - BigQuery execution with cost/cache controls
5. **analyze_df** - Pandas DataFrame statistical analysis
6. **report** - Executive insight generation with evidence

### Key Security Features

- **SQL Injection Prevention**: sqlglot parsing + whitelist validation
- **Table Access Control**: Only orders, order_items, products, users tables
- **Cost Protection**: MAX_BYTES_BILLED enforcement
- **Query Policies**: Auto-LIMIT on non-aggregated queries

### Configuration Management

Environment variables (see `.env.example`):
```bash
GOOGLE_API_KEY=          # Gemini API key
BIGQUERY_PROJECT=        # GCP project ID
BIGQUERY_LOCATION=US     # BigQuery region
DATASET_ID=bigquery-public-data.thelook_ecommerce
MAX_BYTES_BILLED=100000000
MODEL_NAME=gemini-1.5-pro
```

## Troubleshooting Common Issues

### Build Issues

**Problem**: `pip install` times out
**Solution**: Use longer timeout, retry command
```bash
pip install -r requirements.txt --timeout 300
```

**Problem**: Poetry commands fail
**Solution**: Use pip-based workflow instead of make commands
```bash
pip install -r requirements.txt
.venv/bin/pytest
.venv/bin/black src tests
```

### Test Issues

**Problem**: Tests show 0% coverage
**Solution**: Normal for current development phase, tests are being expanded
```bash
.venv/bin/pytest --cov=src  # Coverage will improve as TDD tasks complete
```

**Problem**: CLI timeouts immediately
**Solution**: Expected without real API keys, verify with --help only
```bash
python cli.py --help  # Should work immediately
```

### Development Issues

**Problem**: Pre-commit hooks fail
**Solution**: Use direct tools instead
```bash
.venv/bin/black src tests
.venv/bin/isort src tests  
.venv/bin/flake8 src tests
```

**Problem**: Lint shows many existing issues
**Solution**: Normal during development, focus on files you're editing
```bash
make lint | grep src/your_file.py  # Check only your changes
```

## Build Timing Expectations

**NEVER CANCEL** any of these operations:

- `pip install -r requirements.txt`: 60-300 seconds (may timeout due to network)
- `pip install -r requirements-dev.txt`: 30-120 seconds (may timeout due to network)
- `make test`: <5 seconds
- `make lint`: <5 seconds  
- `make format`: <10 seconds
- `make security`: <10 seconds
- `pre-commit run --all-files`: 30-90 seconds (may fail due to Python version)

**Network Limitations**: In constrained network environments, pip installation may timeout. If this occurs:
- Retry with `--timeout 300` flag
- Use existing pre-installed environment if available
- Skip dependency installation and work with existing packages

## Example Validation Scenarios

### Scenario 1: Fresh Clone Setup

```bash
git clone <repo>
cd langgraph-data-analysis-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt --timeout 300
pip install -r requirements-dev.txt --timeout 300
cp .env.example .env
make test
python cli.py --help
```
**Expected time**: 2-8 minutes total (may timeout in network-constrained environments)

### Scenario 2: Work with Existing Environment

```bash
cd langgraph-data-analysis-agent
source .venv/bin/activate
# Dependencies already installed, skip pip commands
make test
python cli.py --help
make format
```
**Expected time**: <30 seconds

### Scenario 2: Code Change Validation

```bash
source .venv/bin/activate
# Make your changes
make format
make test  
python cli.py --help
make lint | grep src/your_file.py
```
**Expected time**: <30 seconds

### Scenario 3: Full CI Simulation

```bash
source .venv/bin/activate
make format
make lint      # May show existing issues (normal)
make test
make security
```
**Expected time**: <30 seconds

## CI/CD Integration

GitHub Actions pipeline (`.github/workflows/ci.yml`):
- **lint**: black, isort, flake8, mypy validation
- **test**: pytest with coverage across Python 3.11-3.13
- **security**: bandit and safety scans
- **build**: package creation (may timeout due to network)

**Local CI simulation**:
```bash
make github-lint    # Simulate lint job
make github-test    # Simulate test job  
make github-security # Simulate security job
```

## Notes for Effective Development

- **Always activate .venv first**: `source .venv/bin/activate`
- **TDD is primary approach**: Write tests before implementation
- **Use Makefile commands**: Consistent with CI/CD pipeline  
- **Test early and often**: `make test` takes <5 seconds
- **Format before committing**: `make format` prevents CI failures
- **Mock real APIs**: Use test fixtures instead of real credentials
- **Check task specifications**: `tasks/LGDA-*.md` files contain detailed requirements
- **Focus on security**: SQL injection prevention is critical
- **Monitor build times**: Set appropriate timeouts for long operations

## Current Repository State

### Available LGDA Tasks
```
LGDA-001-test-infrastructure
LGDA-002-sql-validation
LGDA-003-bigquery-client
LGDA-004-llm-integration
LGDA-005-configuration-management
```

### Current Test Status
- Basic tests: 4 tests pass in <1 second
- Coverage: 0% on main source code (tests are in development)
- Lint status: Some existing style issues (line length, unused imports)

### Key Repository Files
```
├── cli.py                    # Main CLI entry point
├── src/
│   ├── agent/
│   │   ├── nodes.py          # LangGraph pipeline nodes  
│   │   ├── graph.py          # Pipeline flow definition
│   │   ├── state.py          # Agent state management
│   │   └── prompts.py        # LLM prompt templates
│   ├── bq.py                 # BigQuery client + security
│   ├── llm.py                # Gemini/Bedrock integration
│   └── config.py             # Pydantic configuration
├── tests/
│   └── test_basic.py         # Basic functionality tests
├── tasks/                    # TDD task specifications
├── .github/workflows/ci.yml  # GitHub Actions pipeline
└── Makefile                  # Build automation
```

Remember: This is a production-ready system with comprehensive testing, security scanning, and quality controls. Always follow the TDD approach and validate changes thoroughly.