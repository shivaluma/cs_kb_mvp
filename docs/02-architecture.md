# 02. Architecture

## High-Level System

```mermaid
flowchart TD
  web[React Web] --> api[Go API]
  api --> db[(Postgres)]
  api --> search[Meilisearch]
  api --> ai[Python AI Service]
  ai --> vector[(pgvector or Qdrant)]
```

## Service Responsibilities

| Service | Responsibilities |
| --- | --- |
| React Web | Search UI, SOP detail, admin workflow, dashboards, RBAC-based navigation |
| Go API | Auth/RBAC, SOP CRUD, version workflow, taxonomy, search orchestration, analytics, audit, AI client |
| Python AI | Chunking, embeddings, semantic search, query normalization, suggestions, grounded summaries |
| Postgres | System of record for users, SOPs, versions, sections, taxonomy, events, and audit logs |
| Meilisearch | Keyword search, filters, synonyms/aliases, recent/popular ranking support |
| pgvector/Qdrant | Semantic retrieval over approved SOP chunks |

## Search Flow

```mermaid
sequenceDiagram
  participant User
  participant Web
  participant API
  participant Meili
  participant AI

  User->>Web: Search query + filters
  Web->>API: POST /api/v1/search
  API->>API: Log sop_search
  API->>Meili: Keyword search
  API->>AI: Optional semantic search
  API->>API: Merge and rank
  API->>Web: Results
  User->>Web: Click SOP
  Web->>API: POST /api/v1/analytics/search-click
```

## Publish Flow

```mermaid
sequenceDiagram
  participant Admin
  participant API
  participant DB
  participant Meili
  participant AI

  Admin->>API: Publish version
  API->>DB: Mark version published
  API->>DB: Update sops.current_version_id
  API->>Meili: Upsert lexical document
  API->>AI: Index SOP version
  AI->>AI: Chunk + embed
```

## MVP Deployment

Docker Compose is the default local deployment:

- `web` on port `3000`.
- `api` on port `8080`.
- `ai` on port `8090`.
- `postgres` on port `5432`.
- `meilisearch` on port `7700`.
- `qdrant` on port `6333`.

Production can move the same service boundaries to Kubernetes or the internal platform.
