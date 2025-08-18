.PHONY: help install dev-install test lint format security check-all clean docs

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	poetry install --no-dev

dev-install: ## Install development dependencies
	poetry install
	poetry run pre-commit install

test: ## Run tests
	poetry run pytest --cov=src --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	poetry run pytest tests/unit/ -v

test-integration: ## Run integration tests only
	poetry run pytest tests/integration/ -v -m "not requires_credentials"

test-security: ## Run security tests
	poetry run pytest tests/security/ -v

lint: ## Run linting
	poetry run black --check src tests
	poetry run isort --check-only src tests
	poetry run flake8 src tests
	poetry run mypy src

format: ## Format code
	poetry run black src tests
	poetry run isort src tests

security: ## Run security scans
	poetry run bandit -r src
	poetry run safety check

validate-tasks: ## Validate task specifications
	python scripts/validate_tasks.py

check-adr: ## Check ADR compliance
	find src -name "*.py" | xargs python scripts/check_adr_compliance.py

check-all: lint test security validate-tasks check-adr ## Run all checks

build: ## Build package
	poetry build

clean: ## Clean up generated files
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

docs: ## Build documentation
	poetry run sphinx-build -W -b html docs docs/_build/html

docs-serve: ## Serve documentation locally
	poetry run sphinx-autobuild docs docs/_build/html --port 8080

run-dev: ## Run LGDA in development mode
	poetry run lgda --debug

setup-env: ## Setup development environment
	cp .env.example .env
	@echo "Please edit .env with your configuration"

pre-commit: ## Run pre-commit hooks
	poetry run pre-commit run --all-files

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
