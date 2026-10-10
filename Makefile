# Shortcuts for the local Docker Compose stack.
# Run `make` (or `make help`) to see every command.
#
# Makefile basics:
#   target: prerequisites
#   <TAB>command          <- recipe lines MUST start with a tab, not spaces
# `make up` runs the commands under `up:`. A leading @ hides the command itself
# and prints only its output.

COMPOSE := docker compose

# Windows has no `cp` or `[ -f ]`, so use cmd.exe and its own syntax there.
ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
COPY_ENV := if not exist .env copy .env.example .env >NUL
else
COPY_ENV := [ -f .env ] || cp .env.example .env
endif

# These targets are command names, not files that make should look for.
.PHONY: help up down reset wipe test test-backend test-e2e test-frontend lint lint-backend lint-frontend build logs ps env

# The first target is the default, so plain `make` shows this list.
help:
	@echo Usage: make TARGET
	@echo   up             Start all services in the background (creates .env if missing)
	@echo   down           Stop all services (data is kept)
	@echo   reset          Reload the demo: rebuild the database, load the Golden Case, clock D 21:00
	@echo   wipe           Stop, DELETE database/Redis/node_modules volumes, start fresh
	@echo   test           Run backend and frontend tests (stack must be running: make up)
	@echo   test-backend   Run backend tests only (pytest)
	@echo   test-e2e       Run backend Golden Path E2E tests only (test database)
	@echo   test-frontend  Run frontend tests only (vitest)
	@echo   lint           Run all linters/type checks (stack must be running)
	@echo   lint-backend   Run ruff and mypy on the backend
	@echo   lint-frontend  Type-check the frontend (tsc)
	@echo   build          Production-build the frontend (next build), the same check CI runs
	@echo   logs           Follow logs. One service: make logs s=backend
	@echo   ps             Show service status and health
	@echo   env            Create .env from .env.example if it does not exist

env:
	@$(COPY_ENV)

up: env
	@echo Waiting for all services to become healthy. First start installs dependencies and can take a few minutes.
	$(COMPOSE) up -d --wait
	@echo Frontend: http://localhost:3000   API docs: http://localhost:8000/docs

down:
	$(COMPOSE) down

# Calls POST /demo/reset on the running backend (stack must be running: make up)
reset:
	$(COMPOSE) exec -T backend python -m app.seed

wipe: env
	$(COMPOSE) down -v
	$(COMPOSE) up -d --wait

test: test-backend test-frontend

test-backend:
	$(COMPOSE) exec -T backend pytest

test-e2e:
	$(COMPOSE) exec -T backend pytest tests/e2e -q

test-frontend:
	$(COMPOSE) exec -T frontend npm test

lint: lint-backend lint-frontend

lint-backend:
	$(COMPOSE) exec -T backend sh -c "ruff check . && ruff format --check . && mypy app"

lint-frontend:
	$(COMPOSE) exec -T frontend npm run typecheck

# Safe next to the running dev server: `next dev` writes to .next/dev, the build to .next
build:
	$(COMPOSE) exec -T frontend npm run build

# `s` is an optional service name, e.g. make logs s=frontend
logs:
	$(COMPOSE) logs -f $(s)

ps:
	$(COMPOSE) ps
