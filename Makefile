SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python
PIP := $(BACKEND)/.venv/bin/pip

.PHONY: setup dev dev-backend dev-frontend test test-backend test-frontend lint format \
        sync-data build-features train score seed-config migrate e2e help \
        index-assets import-stats-csv import-kaggle

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort -u

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

test: test-backend test-frontend ## Run all tests

test-backend:
	cd $(BACKEND) && .venv/bin/pytest -q

test-frontend:
	cd $(FRONTEND) && npm run test -- --run

e2e: ## Playwright end-to-end tests (requires running stack or fixture mode)
	cd $(FRONTEND) && npx playwright test

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
