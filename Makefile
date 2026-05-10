SHELL := /bin/sh
PYTHON ?= $(shell command -v python3.12 2>/dev/null || if [ -x "$$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then echo "$$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"; else command -v python3; fi)

ifneq (,$(wildcard .env))
include .env
export
endif

ifneq (,$(wildcard .env.local))
include .env.local
export
endif

.PHONY: dev up down api web ai setup-ai test-api test-ai build-web

dev: up

up:
	docker compose up --build

down:
	docker compose down

api:
	cd apps/cs-kb-api && go run ./cmd/api

web:
	cd apps/cs-kb-web && pnpm run dev

ai:
	cd apps/cs-kb-ai && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload

setup-ai:
	cd apps/cs-kb-ai && $(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "Python 3.12+ is required. Set PYTHON=/path/to/python3.12")'
	cd apps/cs-kb-ai && if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then echo "Using existing Python 3.12 venv"; else rm -rf .venv && $(PYTHON) -m venv .venv; fi
	cd apps/cs-kb-ai && .venv/bin/python -m pip install -r requirements.txt

test-api:
	cd apps/cs-kb-api && go test ./...

test-ai:
	cd apps/cs-kb-ai && .venv/bin/python -m compileall app

build-web:
	cd apps/cs-kb-web && pnpm run build
