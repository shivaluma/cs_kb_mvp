# 10. AI Retrieval Flow

## Scope

The AI service is the production-grade retrieval core for the MVP. It uses Postgres + pgvector as the default store so the same architecture works in Docker Compose and Dokploy.

## Storage

Tables are created by `infra/postgres/init/002_ai_retrieval.sql` and also ensured by the AI service on startup:

- `ai_documents`: stable document identity and current published version pointer.
- `ai_document_versions`: immutable version records with `draft`, `published`, and `archived` lifecycle.
- `ai_chunks`: chunk content, metadata, and `vector(384)` embeddings.
- `ai_retrieval_events`: query logs.
- `ai_audit_events`: upload, publish, and archive logs.
- `taxonomy_intents`: controlled business intents such as `missing_item` and `refund`.
- `search_synonym_groups`: governed synonym groups with `draft`, `in_review`, `active`, and `archived` lifecycle.
- `search_synonym_terms`: phrase-level or intent-level synonym terms with normalized accent-insensitive form.
- `search_synonym_suggestions`: AI/analytics-generated candidates that require human acceptance.

## Version Lifecycle

1. Upload with `status=draft` to create a non-searchable version.
2. Publish with `POST /ai/v1/versions/{version_id}/publish`.
3. Publishing archives the previous published version for the same document.
4. Retrieval defaults to `published` and current-version only.
5. Archive a document with `POST /ai/v1/documents/{document_id}/archive`.

## Retrieval

Endpoint:

```http
POST /ai/v1/retrieve
```

Modes:

- `lexical`: Postgres full-text search with accent-insensitive `immutable_unaccent(content)`.
- `vector`: pgvector cosine search over deterministic 384-dim embeddings.
- `hybrid`: lexical + vector merged with Reciprocal Rank Fusion.

Query normalization is DB-managed. The AI service loads active synonym groups from Postgres with a short cache and returns `query_expansion` in every retrieval response so reviewers can see which canonical intent changed the query.

Synonym types:

- `regular`: two-way equivalence, for example `refund`, `hoan tien`, `boi hoan`.
- `one_way`: user phrase maps to canonical intent only, for example `khong nhan du mon` -> `missing_item`.
- `typo_correction`: misspelling maps to canonical phrase.
- `placeholder`: reserved for future templated query expansion.

The current embedding is deterministic and local, so no external API key is required. It is intentionally shaped like a real embedding backend: replace `app/embedding.py` later with OpenAI, Voyage, bge, or another model without changing API contracts.

## Upload Through Go API

```sh
curl -s \
  -F "file=@samples/missing-item-sop.txt" \
  -F "external_id=sop-food-missing-item-upload" \
  -F "title=Uploaded Food Missing Item SOP" \
  -F "status=published" \
  -F 'metadata={"audience":["customer"],"vertical":"food","category":"case_handling","tags":["missing_item","refund"],"case_reasons":["CR_FOOD_MISSING_ITEM"],"owner_team":"CS Ops"}' \
  http://localhost:8080/api/v1/ai/documents/upload
```

## Hybrid Retrieval Through Go API

```sh
curl -s \
  -H "Content-Type: application/json" \
  -d '{"query":"khach khong nhan du mon co duoc refund khong","mode":"hybrid","limit":5,"filters":{"vertical":["food"],"status":["published"]}}' \
  http://localhost:8080/api/v1/ai/retrieve
```

Every result includes:

- `document_id`
- `version_id`
- `chunk_id`
- `chunk_index`
- `score`
- `lexical_score`
- `vector_score`
- `rank_source`
- `citation`

Every response also includes:

- `normalized_query`
- `query_expansion.strategy`
- `query_expansion.expansions`
- `query_expansion.matched_synonyms`
- `query_expansion.active_synonym_group_count`

## Governed Synonym Flow

List active synonyms:

```sh
curl -s "http://localhost:8080/api/v1/search/synonyms?status=active"
```

Create a draft group:

```sh
curl -s \
  -H "Content-Type: application/json" \
  -d '{"canonical_key":"refund_delay","synonym_type":"one_way","domain":"payment","audience":"customer","status":"draft","created_by":"cs-ops","terms":["tien chua ve vi","chua nhan tien refund"]}' \
  http://localhost:8080/api/v1/search/synonyms
```

Review and approve:

```sh
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"actor":"cs-ops"}' \
  http://localhost:8080/api/v1/search/synonyms/{group_id}/submit-review

curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"actor":"cs-lead"}' \
  http://localhost:8080/api/v1/search/synonyms/{group_id}/approve
```

Sync active groups to Meilisearch runtime settings:

```sh
curl -s -X POST http://localhost:8080/api/v1/search/synonyms/sync
```

Generate suggestions from zero-result retrieval logs:

```sh
curl -s \
  -H "Content-Type: application/json" \
  -d '{"days":14,"min_count":1,"limit":10}' \
  http://localhost:8080/api/v1/search/synonym-suggestions/generate
```

Accept a suggestion into review:

```sh
curl -s \
  -H "Content-Type: application/json" \
  -d '{"canonical_key":"promo_not_applied","synonym_type":"one_way","actor":"cs-ops","submit_review":true}' \
  http://localhost:8080/api/v1/search/synonym-suggestions/{suggestion_id}/accept
```

End-to-end scripts:

- `scripts/e2e-ai-retrieval.sh`
- `scripts/e2e-synonym-governance.sh`

## Dokploy Notes

Required environment variables:

- `DATABASE_URL`: Postgres with pgvector enabled.
- `AI_PORT`: default `8090`.
- `API_PORT`: default `8080`.

The AI service calls `ensure_schema()` on startup, but production deployments should still run SQL migrations from `infra/postgres/init` as part of release management.
