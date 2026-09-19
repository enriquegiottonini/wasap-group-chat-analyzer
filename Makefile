# `make help` lists every rule with its description ("## ..." at the end of the line).
.DEFAULT_GOAL := help
.PHONY: help requirements test lint format clean nb nbs

NOTEBOOKS = notebooks/utils notebooks/01_eda_bronze notebooks/02_eda_platinum

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "%-20s %s\n", $$1, $$2}'

# --- Environment and code ------------------------------------------------------

requirements: ## Install Python dependencies (creates .venv)
	uv sync

test: ## Run tests
	uv run pytest tests

lint: ## Check formatting and lint with ruff
	uv run ruff format --check
	uv run ruff check

format: ## Fix lint and format with ruff
	uv run ruff check --fix
	uv run ruff format

clean: ## Delete caches and data/raw, data/interim, data/processed (keeps .gitkeep)
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete
	find data/raw data/interim data/processed -mindepth 1 ! -name .gitkeep -delete

# --- Notebooks -----------------------------------------------------------------

nb: ## Export one marimo notebook to .ipynb with outputs (NOTEBOOK=notebooks/<name>, without .py)
	uv run marimo export ipynb $(NOTEBOOK).py -o $(NOTEBOOK).ipynb --include-outputs

nbs: ## Export every marimo notebook to .ipynb with outputs
	@for nb in $(NOTEBOOKS); do $(MAKE) --no-print-directory nb NOTEBOOK=$$nb || exit 1; done
