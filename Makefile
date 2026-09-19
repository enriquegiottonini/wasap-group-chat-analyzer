# `make help` lists every rule with its description ("## ..." at the end of the line).
.DEFAULT_GOAL := help
.PHONY: help requirements test lint format clean nb nbs ingest anonymize process leak-check data

NOTEBOOKS = notebooks/utils notebooks/01_eda_bronze notebooks/02_eda_silver

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

nbs: ## Export every marimo notebook (that exists yet) to .ipynb with outputs
	@for nb in $(NOTEBOOKS); do \
		[ -f $$nb.py ] || continue; \
		$(MAKE) --no-print-directory nb NOTEBOOK=$$nb || exit 1; \
	done

# --- Pipeline ------------------------------------------------------------------

# CHAT: slug of the chat to work on (default: `chat` in params.yml); every chat lives in
#       its own data/{raw,interim,processed}/<chat>/ folder.
# ZIP: WhatsApp export to ingest (default: the zip registered for CHAT in `chats`).
# ON_EXISTS: skip | overwrite | error (default: source.on_exists in params.yml).
CHAT ?=
ZIP ?=
ON_EXISTS ?=
export CHAT

data: ingest anonymize process ## Run the whole pipeline for CHAT: ingest → anonymize → process

anonymize: ## Parse data/raw/<chat>/ into interim bronze.parquet (real names, local only) and messages_anon.parquet
	uv run python -m wasap_group_analyzer.jobs.anonymize_job $(if $(CHAT),--chat "$(CHAT)")

process: ## Build the tidy silver datasets in data/processed/<chat>/ (messages, tokens, emojis)
	uv run python -m wasap_group_analyzer.jobs.process_job $(if $(CHAT),--chat "$(CHAT)")

leak-check: ## Fail if a real name shows up in interim/processed data, notebooks or references (SHOW=1 lists them)
	uv run python -m wasap_group_analyzer.jobs.leak_check_job $(if $(CHAT),--chat "$(CHAT)") $(if $(SHOW),--show)

ingest: ## Copy a WhatsApp export to data/raw/<chat>/, unzip it and write FUENTE.txt (CHAT=, ZIP=, ON_EXISTS=)
	uv run python -m wasap_group_analyzer.jobs.ingest_job $(if $(CHAT),--chat "$(CHAT)") \
		$(if $(ZIP),--zip "$(ZIP)") $(if $(ON_EXISTS),--on-exists "$(ON_EXISTS)")
