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
.PHONY: help up down reset test logs ps env

# The first target is the default, so plain `make` shows this list.
help:
	@echo Usage: make TARGET
	@echo   up      Start all services in the background (creates .env if missing)
	@echo   down    Stop all services (data is kept)
	@echo   reset   Stop, DELETE database/Redis/node_modules volumes, start fresh
	@echo   test    Run backend tests (stack must be running: make up)
	@echo   logs    Follow logs. One service: make logs s=backend
	@echo   ps      Show service status and health
	@echo   env     Create .env from .env.example if it does not exist

env:
	@$(COPY_ENV)

up: env
	$(COMPOSE) up -d
	@echo Frontend: http://localhost:3000   API docs: http://localhost:8000/docs
	@echo First start installs dependencies and can take a few minutes. Check with: make ps

down:
	$(COMPOSE) down

reset: env
	$(COMPOSE) down -v
	$(COMPOSE) up -d

test:
	$(COMPOSE) exec -T backend pytest

# `s` is an optional service name, e.g. make logs s=frontend
logs:
	$(COMPOSE) logs -f $(s)

ps:
	$(COMPOSE) ps
