# 00. General Information

## Product

CS SOP Knowledge Base is an internal system for CS teams to search and use approved SOPs with version governance, usage analytics, and an AI-ready data structure.

## MVP Principle

Do not start with a chatbot. The MVP value is:

1. Centralized SOP website.
2. Latest published version as the source of truth.
3. Fast keyword search with filters.
4. Usage and search-quality analytics.
5. Structured content that can later power AI retrieval.

## Repo Layout

| Path | Purpose |
| --- | --- |
| `apps/cs-kb-web` | React + Vite + pnpm UI for agents, leads, and admins, using shadcn/ui v4 and Tailwind CSS v4 |
| `apps/cs-kb-api` | Go API for SOP, search, analytics, workflow, and AI orchestration |
| `apps/cs-kb-ai` | Python FastAPI AI/retrieval service |
| `infra/postgres` | Local database schema/bootstrap |
| `docs` | Product and engineering handoff docs |

## MVP Roles

| Role | Permissions |
| --- | --- |
| Agent | Search, read SOP, copy macro, submit feedback |
| Lead | Agent permissions, analytics, review drafts |
| SOP Admin | CRUD SOP, taxonomy management, create drafts |
| Super Admin | User, role, and system config management |

## First Local Run

```sh
cp .env.example .env
docker compose up --build
```

Use Docker Compose for the full stack. For app-only development, each app also supports native local commands documented in `docs/05-local-development.md`.
