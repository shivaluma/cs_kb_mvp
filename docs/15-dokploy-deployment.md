# Dokploy Deployment

This project is deployed as three Dokploy apps plus managed infrastructure services.

## Services

### `cs-kb-web`

- Build context: `apps/cs-kb-web`
- Dockerfile: `Dockerfile`
- Internal port: `3000`
- Health path: `/healthz`

Environment:

```env
API_BASE_URL=https://<api-domain>
```

`API_BASE_URL` is injected at container start into `/env.js`, so changing the API domain does not require rebuilding the React bundle.

### `cs-kb-api`

- Build context: `apps/cs-kb-api`
- Dockerfile: `Dockerfile`
- Internal port: `8080`
- Health path: `/healthz`

Environment:

```env
API_ADDR=:8080
DATABASE_URL=postgres://...
MEILI_HOST=https://<meili-host-or-internal-url>
MEILI_MASTER_KEY=...
AI_BASE_URL=https://<ai-domain-or-internal-url>
SEED_DEMO_SOPS=false
DATABASE_CONNECT_TIMEOUT_SECONDS=10
LOG_LEVEL=info
```

`DATABASE_URL` must point to Postgres with `pgvector` installed.
Set `LOG_LEVEL=debug` temporarily when debugging Dokploy upstream issues. API logs are JSON and include `request_id`, HTTP status, latency, AI proxy target/status, and Meilisearch failures.

### `cs-kb-ai`

- Build context: `apps/cs-kb-ai`
- Dockerfile: `Dockerfile`
- Internal port: `8090`
- Health path: `/healthz`

Environment:

```env
DATABASE_URL=postgres://...
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_EXTRACTION_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_REFINE_MODEL=google/gemini-3-flash-preview
OPENROUTER_VISION_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_METADATA_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_CHAT_SIMPLE_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_CHAT_POLICY_MODEL=moonshotai/kimi-k2.5
OPENROUTER_CHAT_HIGH_RISK_MODEL=moonshotai/kimi-k2.5
OPENROUTER_CHAT_COMPLEX_MODEL=moonshotai/kimi-k2.6
OPENROUTER_CHAT_FALLBACK_MODEL=moonshotai/kimi-k2.6
EMBEDDING_PROVIDER=local_hash
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
PUBLIC_APP_URL=https://<web-domain>
QDRANT_URL=https://<qdrant-domain-or-internal-url> # optional, shown as not configured when empty
QDRANT_API_KEY=...
```

The AI service owns extraction, embeddings, retrieval, and grounded answer generation. Upload can succeed while extraction returns a recoverable failed draft.

## Infrastructure

Recommended Dokploy managed/external services:

- Postgres with `pgvector`
- Meilisearch
- Optional Qdrant only if later moving vector storage out of Postgres

## Routing

Expose public domains for:

- Web: user-facing dashboard
- API: consumed by browser and web app
- AI: can be internal-only if the API can reach it

If AI is internal-only, set `AI_BASE_URL` in API to the Dokploy internal service URL.
