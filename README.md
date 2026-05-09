# CS SOP Knowledge Base MVP

Internal knowledge base for CS teams to search, govern, version, and analyze SOP usage. The MVP is intentionally built around structured SOP content and version control first, then AI retrieval as an enhancement layer.

## Apps

- `apps/cs-kb-web`: React + TypeScript + Vite + pnpm UI, using shadcn/ui v4 and Tailwind CSS v4.
- `apps/cs-kb-api`: Go API for auth/RBAC placeholder, SOP read/search, workflow, analytics, and AI orchestration contracts.
- `apps/cs-kb-ai`: Python FastAPI service for semantic search, suggestions, and grounded answer contracts.
- `infra/postgres`: Initial database schema for the MVP domain model.
- `docs`: Product, architecture, implementation, and operating guidelines.

## Quick Start

```sh
cp .env.example .env
docker compose up --build
```

Open:

- Web: http://localhost:3000
- API health: http://localhost:8080/healthz
- AI health: http://localhost:8090/healthz
- Meilisearch: http://localhost:7700
- Qdrant: http://localhost:6333

## Local Development Without Docker

```sh
cd apps/cs-kb-api
go run ./cmd/api
```

```sh
cd apps/cs-kb-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

```sh
cd apps/cs-kb-web
pnpm install
pnpm run dev
```

## Current State

This repo is a runnable MVP foundation, not the full production implementation. It includes:

- Multi-app monorepo layout.
- Docker Compose stack.
- Structured SOP seed data.
- Search UI with filters and detail panel.
- Go API contracts for SOP/search/analytics/AI handoff.
- Python AI service contracts with citation-first response shapes.
- AI document upload and hybrid retrieval backed by Postgres + pgvector.
- Database schema draft and implementation docs.

## Test AI Retrieval

After `docker compose up --build`, run:

```sh
./scripts/e2e-ai-retrieval.sh
```

This uploads `samples/missing-item-sop.txt` through the Go API and runs hybrid retrieval with chunk citations.

Read [docs/00-general-information.md](docs/00-general-information.md) first.
