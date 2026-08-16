.PHONY: help test test-python test-sql test-all setup-python setup-local teardown-local format lint check clean

# Default target
help:
	@echo "Community Calendar Test Suite"
	@echo ""
	@echo "Targets:"
	@echo "  make test            - Run Python tests"
	@echo "  make test-python     - Run Python tests (pytest via uv)"
	@echo "  make test-sql        - Run database tests (local Supabase via pgTAP)"
	@echo "  make format          - Auto-format Python code (ruff format)"
	@echo "  make lint            - Lint Python code (ruff check; type checkers gate)"
	@echo "  make check           - Run lint + Python tests"
	@echo "  make setup-python    - Create venv and install dependencies (uv sync)"
	@echo "  make setup-local     - Start local Supabase and apply schema"
	@echo "  make teardown-local  - Stop local Supabase"
	@echo "  make clean           - Clean test artifacts"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - uv (install with: curl -LsSf https://astral.sh/uv/install.sh | sh)"
	@echo "  - Supabase CLI installed (for database tests)"
	@echo "  - PostgreSQL client (psql) for local database access"

# Run default tests
test: test-python

# Alias for test
test-all: test

# Setup Python environment with uv
setup-python:
	@echo "Setting up Python environment with uv..."
	@uv sync
	@echo "✓ Dependencies installed"
	@echo ""
	@echo "Activate venv with: source .venv/bin/activate"

# Run Python tests
test-python:
	@echo "Running Python tests..."
	@uv run env -u PYTHONPATH pytest tests/ -v

# Auto-format Python code
format:
	@echo "Formatting Python code..."
	@uv run ruff format .
	@echo "✓ Formatted"

# Lint Python code. Ruff (format + check) and all four type checkers gate.
# `uv sync` runs first so a stale venv (e.g. after removing a dependency) can't
# mask diagnostics with leftover installed packages — the checkers must resolve
# against the exact lockfile state, not whatever uv run leaves behind.
lint:
	@echo "Syncing environment to lockfile..."
	@uv sync --quiet
	@echo "✓ environment synced"
	@echo ""
	@echo "Running ruff format check..."
	@uv run ruff format --check .
	@echo "✓ ruff formatted"
	@echo ""
	@echo "Running ruff check..."
	@uv run ruff check .
	@echo "✓ ruff clean"
	@echo ""
	@echo "Running type checkers..."
	@status=0; \
	for checker in "pyright" "ty check" "pyrefly check" "zuban mypy ."; do \
		echo "  → $$checker"; \
		uv run $$checker >/tmp/cc-lint-$$(echo $$checker | tr ' ' '_').log 2>&1 || status=$$?; \
		tail -2 /tmp/cc-lint-$$(echo $$checker | tr ' ' '_').log | sed 's/^/    /'; \
	done; \
	echo ""; \
	if [ $$status -ne 0 ]; then \
		echo "❌ Type checkers reported diagnostics (gating)."; \
	else \
		echo "✓ Type checkers clean"; \
	fi; \
	exit $$status

# Lint + tests
check: lint test-python

# Run database tests (requires prepared local Supabase project DB)
test-sql:
	@echo "Running database tests..."
	@if ! supabase status > /dev/null 2>&1; then \
		echo "ERROR: Local Supabase is not running."; \
		echo "Run: make setup-local"; \
		exit 1; \
	fi
	@supabase test db supabase/tests/

# Setup local Supabase environment
setup-local:
	@echo "Starting local Supabase..."
	supabase start
	@echo "Applying migrations..."
	supabase db reset
	@echo ""
	@echo "✓ Local environment ready"
	@echo "Run: make test-sql"

# Teardown local Supabase
teardown-local:
	@echo "Stopping local Supabase..."
	supabase stop

# Clean test artifacts
clean:
	@echo "Cleaning test artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"
