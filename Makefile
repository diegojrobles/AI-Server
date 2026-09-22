# AI-Server developer commands.
#
# Every target runs tools out of the local .venv, so nothing here depends on
# the calling shell having a virtualenv activated. The dev environment is
# bootstrapped on demand and rebuilt only when the requirements files change.
#
#     make help     list every target
#     make check    what CI runs: lint, tests, secret scan
#
# Keep these targets in step with .github/workflows/test.yml: a green `make
# check` locally should mean a green pipeline.

PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
# Console scripts are invoked as modules: `.venv/bin/pip` is a shebang script
# that breaks if the checkout moves, `python -m pip` never does.
PY := $(BIN)/python
DEV_STAMP := $(VENV)/.dev-deps
RUN_STAMP := $(VENV)/.run-deps

# The app is imported as `app.*` / `config.*` from the repo root.
export PYTHONPATH := .

.DEFAULT_GOAL := help

.PHONY: help
help: ## List the available targets
	@echo "AI-Server — make targets:"
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'

$(VENV):
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip

# Test/lint environment: base + pytest + ruff, deliberately without torch.
$(DEV_STAMP): requirements-dev.txt requirements-base.txt | $(VENV)
	$(PY) -m pip install -q -r requirements-dev.txt
	@touch $@

# Full runtime, including the local inference stack. Slow: pulls torch.
$(RUN_STAMP): requirements.txt requirements-base.txt | $(VENV)
	$(PY) -m pip install -q -r requirements.txt
	@touch $@

.PHONY: dev
dev: $(DEV_STAMP) ## Install the test and lint dependencies
	@echo "dev environment ready: $(BIN)"

.PHONY: install
install: $(RUN_STAMP) ## Install the full runtime dependencies (includes torch)
	@echo "runtime environment ready: $(BIN)"

.PHONY: test
test: $(DEV_STAMP) ## Run the test suite (offline, no model download)
	$(PY) -m pytest

.PHONY: coverage
coverage: $(DEV_STAMP) ## Run the tests with a coverage report
	$(PY) -m pytest --cov=app --cov=config --cov-report=term-missing

.PHONY: lint
lint: $(DEV_STAMP) ## Check style and formatting without changing files
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

.PHONY: format
format: $(DEV_STAMP) ## Apply formatting and the autofixable lint rules
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

.PHONY: scan
scan: ## Scan tracked files and full history for secrets
	$(PYTHON) scripts/secret_scan.py --all

.PHONY: audit
audit: $(DEV_STAMP) ## Audit dependencies for known CVEs
	$(PY) -m pip install -q pip-audit==2.7.3
	$(PY) -m pip_audit -r requirements-base.txt -r requirements-dev.txt --strict

.PHONY: check
check: lint test scan ## Everything CI enforces, in one command
	@echo "check: ok"

.PHONY: hooks
hooks: ## Enable the pre-commit secret scan for this clone
	git config core.hooksPath .githooks
	@echo "hooks: core.hooksPath -> .githooks"

.PHONY: run
run: $(RUN_STAMP) ## Start the server (HOST and PORT come from .env)
	$(PY) run.py

.PHONY: docker
docker: ## Build and start the container
	docker compose up --build

.PHONY: clean
clean: ## Remove caches and test artifacts (keeps .venv)
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
