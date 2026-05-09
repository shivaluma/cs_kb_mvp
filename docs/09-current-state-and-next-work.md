# 09. Current State and Next Work

## Implemented in This Baseline

- Monorepo layout for `cs-kb-web`, `cs-kb-api`, `cs-kb-ai`, `infra`, and `docs`.
- Docker Compose for web, API, AI, Postgres with pgvector, Meilisearch, and Qdrant.
- Go API with in-memory seed SOPs and these endpoints:
  - `GET /healthz`
  - `GET /api/v1/homepage`
  - `GET /api/v1/sops`
  - `GET /api/v1/sops/{id}`
  - `POST /api/v1/search`
  - `POST /api/v1/ai/suggest`
- React web MVP screen redesigned with shadcn/ui v4, Tailwind CSS v4, pnpm, search, filters, SOP detail, macro copy, and AI suggestion panel.
- Python AI service with contract endpoints and citation-first stub behavior.
- Production-grade AI retrieval flow using Postgres + pgvector:
  - Multipart document upload for TXT/MD/PDF/DOCX.
  - Text extraction, section-aware chunking, deterministic 384-dim embeddings.
  - Document/version lifecycle with draft, published, archived.
  - Latest published version retrieval only by default.
  - Hybrid retrieval with Postgres FTS, pgvector cosine search, and RRF merge.
  - Chunk-level citations and retrieval/audit logs.
- Governed search relevance loop:
  - Controlled taxonomy intents and DB-managed synonym groups.
  - Synonym lifecycle: draft, in review, active, archived.
  - Accent-insensitive Vietnamese query normalization.
  - Runtime query expansion with explainability in `query_expansion`.
  - Meilisearch synonym sync through the Go API.
  - Zero-result log based synonym suggestions and human acceptance flow.
- Postgres schema draft for users, roles, SOPs, versions, sections, taxonomy, analytics, audit logs, and vector chunks.

## Intentional Stubs

| Area | Current State | Next Implementation |
| --- | --- | --- |
| Auth/RBAC | UI/API contract only | Add SSO or email/password fallback and server-side permission middleware |
| Persistence | API uses in-memory seed data | Wire Go API to Postgres repositories |
| Keyword search | Deterministic in-memory scoring plus Meilisearch synonym sync endpoint | Index published SOP documents into Meilisearch |
| Semantic search | Deterministic local embeddings + pgvector retrieval | Replace `app/embedding.py` with managed embedding model when approved |
| Workflow | Docs/schema only | Implement draft, review, publish, archive APIs |
| Analytics | Schema and UI intent only | Insert search/view/click/copy events |
| Migration | Guideline only | Build Excel importer with validation report |

## Recommended Next Steps

1. Add Go repository layer for Postgres.
2. Implement auth middleware and role checks.
3. Implement SOP CRUD and version lifecycle.
4. Add Meilisearch indexing on publish.
5. Add analytics writes for search, click, view, and macro copy.
6. Add frontend document upload/retrieval/synonym QA screen.
7. Build Excel migration CLI.
8. Replace deterministic embedding with production embedding provider or self-host model.

## Product Guardrails to Preserve

- Agents only see latest published SOP versions.
- Draft and archived SOPs never enter public search or AI retrieval.
- Published versions are immutable.
- AI answers must cite SOP/version/section.
- AI downtime must not block keyword search or SOP reading.
