SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python
PIP := $(BACKEND)/.venv/bin/pip

E2E_DB ?= $(CURDIR)/backend/rosterlab-e2e.db

.PHONY: setup dev dev-backend dev-frontend test test-backend test-frontend lint format \
        sync-data build-features train score seed-config migrate e2e help \
        index-assets import-stats-csv import-kaggle seed-demo visual-qa worker \
        purge-fixtures import-contracts contract-coverage

# `[a-z-]+` missed targets containing a digit or ending the alternation early, so
# `e2e` never appeared. Match the full target token instead.
help:
	@grep -E '^[a-z0-9][a-z0-9-]*:' Makefile | sed 's/:.*//' | sort -u

setup: ## Create backend venv, install backend + frontend dependencies
	python3.12 -m venv $(BACKEND)/.venv 2>/dev/null || python3.11 -m venv $(BACKEND)/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm install
	@test -f .env || cp .env.example .env
	@echo "Setup complete. Edit .env, then run: make migrate && make sync-data && make dev"

migrate: ## Apply database migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

dev: ## Run backend (:8000) and frontend (:3000) together
	@trap 'kill 0' EXIT; \
	(cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

dev-backend:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd $(FRONTEND) && npm run dev

worker: ## Run the background scheduler locally (the same one docker compose runs)
	cd $(BACKEND) && .venv/bin/python -m app.worker

test: test-backend test-frontend ## Run all tests

# Mirrors CI exactly (see .github/workflows/ci.yml) so a green local run means a green
# CI run — including the coverage floor.
test-backend:
	cd $(BACKEND) && .venv/bin/pytest -q --cov=app --cov-report=term-missing --cov-fail-under=68

test-frontend:
	cd $(FRONTEND) && npm run test -- --run

import-contracts: ## Import contracts from the configured provider and report ROSTER-side coverage
	cd $(BACKEND) && .venv/bin/python -m app.cli sync-contracts

contract-coverage: ## Report contract coverage without importing anything
	cd $(BACKEND) && .venv/bin/python -m app.cli contract-coverage

purge-fixtures: ## List test-run leftovers in the dev DB (add APPLY=1 to delete)
	cd $(BACKEND) && .venv/bin/python -m app.cli purge-fixtures $(if $(APPLY),--apply,)

seed-demo: ## Build a DEDICATED e2e database from the synthetic demo league
	rm -f "$(E2E_DB)"
	cd $(BACKEND) && DATABASE_URL="sqlite:///$(E2E_DB)" .venv/bin/alembic upgrade head
	cd $(BACKEND) && DATABASE_URL="sqlite:///$(E2E_DB)" .venv/bin/python -m app.cli seed-config
	cd $(BACKEND) && DATABASE_URL="sqlite:///$(E2E_DB)" .venv/bin/python -m app.cli seed-demo
	cd $(BACKEND) && DATABASE_URL="sqlite:///$(E2E_DB)" .venv/bin/python -m app.cli train
	cd $(BACKEND) && DATABASE_URL="sqlite:///$(E2E_DB)" .venv/bin/python -m app.cli score

e2e: seed-demo ## Playwright end-to-end tests against the dedicated demo database
	cd $(FRONTEND) && DATABASE_URL="sqlite:///$(E2E_DB)" npx playwright test

visual-qa: ## Screenshot every route at every supported viewport; fails on problems
	cd $(FRONTEND) && node ../scripts/visual_qa.mjs $(OUT)

lint: ## Ruff + mypy + eslint + tsc
	cd $(BACKEND) && .venv/bin/ruff check app tests && .venv/bin/mypy app
	cd $(FRONTEND) && npm run lint && npx tsc --noEmit

format:
	cd $(BACKEND) && .venv/bin/ruff format app tests && .venv/bin/ruff check --fix app tests

sync-data: ## Ingest current NBA data via nba_api (network required)
	cd $(BACKEND) && .venv/bin/python -m app.cli sync-all

build-features: ## Build modeling features from ingested data
	cd $(BACKEND) && .venv/bin/python -m app.cli build-features

train: ## Train player-impact model and archetypes
	cd $(BACKEND) && .venv/bin/python -m app.cli train

score: ## Score current players and compute team needs
	cd $(BACKEND) && .venv/bin/python -m app.cli score

seed-config: ## Load salary-cap parameter YAML into the database
	cd $(BACKEND) && .venv/bin/python -m app.cli seed-config

index-assets: ## Index local player photos / team logos into the media manifest
	cd $(BACKEND) && .venv/bin/python -m app.cli index-assets

import-stats-csv: ## Import the user-supplied season-totals CSV (data/imports/)
	cd $(BACKEND) && .venv/bin/python -m app.cli import-stats-csv

import-kaggle: ## Import historical enrichment from the Kaggle basketball dataset
	cd $(BACKEND) && .venv/bin/python -m app.cli import-kaggle
