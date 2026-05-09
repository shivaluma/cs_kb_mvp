SHELL := /bin/sh

.PHONY: dev up down api web ai test-api test-ai build-web

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
	cd apps/cs-kb-ai && uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload

test-api:
	cd apps/cs-kb-api && go test ./...

test-ai:
	cd apps/cs-kb-ai && python3 -m compileall app

build-web:
	cd apps/cs-kb-web && pnpm run build
