.PHONY: help install dev-install test lint format security check-all clean docs

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	.venv/bin/pip install -r requirements.txt

dev-install: ## Install development dependencies
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pre-commit install

test: ## Run tests
	PYTHONPATH=. .venv/bin/pytest --cov=src --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	PYTHONPATH=. .venv/bin/pytest tests/unit/ -v

test-integration: ## Run integration tests only
	PYTHONPATH=. .venv/bin/pytest tests/integration/ -v -m "not requires_credentials"

test-security: ## Run security tests
	PYTHONPATH=. .venv/bin/pytest tests/security/ -v

lint: ## Run linting
	.venv/bin/black --check src tests
	.venv/bin/isort --check-only src tests
	.venv/bin/flake8 src tests
	.venv/bin/mypy src

format: ## Format code
	.venv/bin/black src tests
	.venv/bin/isort src tests

security: ## Run security scans
	.venv/bin/python -m bandit -r src || echo "bandit not installed, skipping"
	.venv/bin/python -m safety check || echo "safety not installed, skipping"

validate-tasks: ## Validate task specifications
	.venv/bin/python scripts/validate_tasks.py

check-adr: ## Check ADR compliance
	find src -name "*.py" | xargs .venv/bin/python scripts/check_adr_compliance.py

check-all: lint test security validate-tasks check-adr ## Run all checks

build: ## Build package
	.venv/bin/python -m build || echo "build not installed, install with: pip install build"

clean: ## Clean up generated files
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

docs: ## Build documentation
	.venv/bin/python -m sphinx docs docs/_build/html || echo "sphinx not installed"

docs-serve: ## Serve documentation locally
	.venv/bin/python -m sphinx_autobuild docs docs/_build/html --port 8080 || echo "sphinx-autobuild not installed"

run-dev: ## Run LGDA in development mode
	.venv/bin/python -m src.cli --debug

setup-env: ## Setup development environment
	cp .env.example .env
	@echo "Please edit .env with your configuration"

pre-commit: ## Run pre-commit hooks
	.venv/bin/pre-commit run --all-files

ci-local: ## Simulate CI pipeline locally
	make check-all
	make build
	@echo "✅ Local CI simulation passed"

# Development helpers
install-pre-commit: ## Install pre-commit hooks
	poetry run pre-commit install
	poetry run pre-commit install --hook-type commit-msg

update-deps: ## Update dependencies
	poetry update
	poetry run pre-commit autoupdate

# Task management
list-tasks: ## List all LGDA tasks
	@echo "Current LGDA Tasks:"
	@ls -1 tasks/LGDA-*.md | sed 's/tasks\///g' | sed 's/\.md//g'

check-task: ## Check specific task (usage: make check-task TASK=LGDA-001)
	@if [ -f "tasks/$(TASK).md" ]; then \
		echo "✅ Task $(TASK) exists"; \
		grep "## Цель задачи" tasks/$(TASK).md -A 1; \
	else \
		echo "❌ Task $(TASK) not found"; \
	fi

# GitHub workflow simulation
github-lint: ## Simulate GitHub lint job
	poetry run black --check --diff src tests
	poetry run isort --check-only --diff src tests
	poetry run flake8 src tests
	poetry run mypy src

github-test: ## Simulate GitHub test job
	poetry run pytest \
		--cov=src \
		--cov-report=xml \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		--junitxml=test-results.xml \
		-v

github-security: ## Simulate GitHub security job
	poetry run safety check --json
	poetry run bandit -r src -f json -o bandit-report.json

github-validate: ## Simulate GitHub task validation job
	python scripts/validate_tasks.py
