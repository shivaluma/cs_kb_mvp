# 09. Current State and Next Work

## Implemented in This Baseline

- Monorepo layout for `cs-kb-web`, `cs-kb-api`, `cs-kb-ai`, `infra`, and `docs`.
- Docker Compose for web, API, AI, Postgres with pgvector, Meilisearch, and Qdrant.
- Go API with Postgres-backed SOP/version persistence, Meilisearch orchestration, AI proxying, and these endpoints:
  - `GET /healthz`
  - `GET /api/v1/homepage`
  - `GET /api/v1/sops`
  - `GET /api/v1/sops/{id}`
  - `POST /api/v1/search`
  - `POST /api/v1/ai/suggest`
- React web MVP screen redesigned with shadcn/ui v4, Tailwind CSS v4, pnpm, search, filters, SOP detail, macro copy, and AI suggestion panel.
- Python AI service with contract endpoints and citation-first stub behavior.
- Production-grade AI retrieval flow using Postgres + pgvector:
  - Multipart document upload for TXT/MD/PDF/DOCX/XLSX/XLSM/XLS and image assets.
  - Document classification for text SOP, policy table, workflow/diagram, asset, macro/script, and unknown sources.
  - Text and spreadsheet extraction, section/sheet/row-aware chunking, deterministic 384-dim embeddings.
  - Workflow PDF draft extraction into granular units such as `decision_point`, `workflow_step`, `macro_script`, `operational_note`, and `security_note`.
  - Optional OpenRouter chat-completions extractor for workflow drafts, with deterministic heuristic fallback when `OPENROUTER_API_KEY` is not configured.
  - Editable extraction review units with confidence, source page metadata, review status, audit log, and regenerated embeddings before publish.
  - Document/version lifecycle with draft, published, archived.
  - Latest published version retrieval only by default.
  - Hybrid retrieval with Postgres FTS, pgvector cosine search, RRF merge, and workflow-aware intent reranking.
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
| Keyword search | Meilisearch indexes exist for SOP/documents, but eval uploads published directly through AI only sync semantic retrieval | Route all publish paths through Go orchestration or add AI publish webhook to Meili |
| Semantic search | Deterministic local embeddings + pgvector retrieval | Replace `app/embedding.py` with managed embedding model when approved |
| Workflow | Document/version draft, publish, archive, and extraction-unit edit APIs exist | Add approval comments, reviewer assignment, and richer extraction-unit edit history UI |
| Analytics | Schema and UI intent only | Insert search/view/click/copy events |
| Migration | Excel upload parser supports sheet/row chunks and review units | Build batch Excel importer with validation report |
| Diagram vision | Text-layer workflow PDFs become structured draft units; scanned diagrams/images are classified and kept in review | Add OCR/layout/vision extraction with bbox source highlighting |

## Recommended Next Steps

1. Implement auth middleware and role checks.
2. Route every document publish path through Go API in production usage; direct AI publish should remain an internal/dev-only path.
3. Add analytics writes for search, click, view, and macro copy.
4. Build batch Excel migration CLI for bulk SOP onboarding and QA reports.
5. Add OCR/layout/vision extraction with bbox source highlighting for scanned PDFs/images.
6. Replace deterministic embedding with production embedding provider or self-host model.

## Product Guardrails to Preserve

- Agents only see latest published SOP versions.
- Draft and archived SOPs never enter public search or AI retrieval.
- Published versions are immutable.
- AI answers must cite SOP/version/section.
- AI downtime must not block keyword search or SOP reading.
