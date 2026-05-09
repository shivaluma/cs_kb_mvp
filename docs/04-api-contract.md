# 04. API Contract

Base path: `/api/v1`

## System

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | API health |

## SOP

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/sops` | List latest visible SOPs |
| `GET` | `/sops/{id}` | Get SOP detail |
| `POST` | `/sops` | Create SOP shell and first draft |
| `POST` | `/sops/{id}/versions` | Create new draft version |
| `GET` | `/sops/{id}/versions` | Version history |
| `POST` | `/sop-versions/{id}/submit-review` | Submit draft for review |
| `POST` | `/sop-versions/{id}/publish` | Publish version |
| `POST` | `/sops/{id}/archive` | Archive SOP |

## Search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/search` | Keyword/hybrid search with filters |
| `GET` | `/search/taxonomy/intents` | List controlled search intents |
| `GET` | `/search/synonyms` | List synonym groups |
| `POST` | `/search/synonyms` | Create synonym group draft |
| `GET` | `/search/synonyms/active` | List active runtime synonym groups |
| `POST` | `/search/synonyms/{id}/submit-review` | Submit synonym group for review |
| `POST` | `/search/synonyms/{id}/approve` | Activate synonym group |
| `POST` | `/search/synonyms/{id}/archive` | Archive synonym group |
| `POST` | `/search/synonyms/sync` | Sync active synonym settings to Meilisearch |
| `GET` | `/search/synonym-suggestions` | List AI/analytics synonym suggestions |
| `POST` | `/search/synonym-suggestions/generate` | Generate synonym suggestions from zero-result logs |
| `POST` | `/search/synonym-suggestions/{id}/accept` | Accept a suggestion into synonym review |
| `POST` | `/analytics/search-click` | Record result click |

Example request:

```json
{
  "query": "khong nhan du mon",
  "filters": {
    "audience": ["customer"],
    "vertical": ["food"],
    "tags": ["missing_item"]
  },
  "include_semantic": true
}
```

## AI

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/ai/suggest` | Suggest SOPs or answer with citations |
| `GET` | `/ai/documents` | Proxy list indexed AI documents |
| `POST` | `/ai/documents/upload` | Proxy multipart document upload and indexing |
| `GET` | `/ai/documents/{id}/versions` | Proxy document version history |
| `POST` | `/ai/documents/{id}/archive` | Proxy document archive |
| `POST` | `/ai/versions/{id}/publish` | Proxy version publish |
| `POST` | `/ai/retrieve` | Proxy hybrid retrieval |

AI service internal base path: `/ai/v1`

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/documents` | List indexed documents |
| `POST` | `/documents/upload` | Upload PDF/DOCX/TXT/MD, extract text, chunk, embed, and create version |
| `GET` | `/documents/{id}/versions` | List document versions |
| `POST` | `/documents/{id}/archive` | Archive document and hide from retrieval |
| `POST` | `/versions/{id}/publish` | Publish version and archive previous published version |
| `POST` | `/retrieve` | Hybrid retrieval using lexical + pgvector + RRF |
| `GET` | `/search/taxonomy/intents` | List controlled search intents |
| `GET` | `/search/synonyms` | List synonym groups |
| `POST` | `/search/synonyms` | Create synonym group draft |
| `GET` | `/search/synonyms/active` | List active runtime synonym groups |
| `POST` | `/search/synonyms/{id}/submit-review` | Submit synonym group for review |
| `POST` | `/search/synonyms/{id}/approve` | Activate synonym group |
| `POST` | `/search/synonyms/{id}/archive` | Archive synonym group |
| `GET` | `/search/synonyms/meilisearch` | Build Meilisearch synonym settings payload |
| `GET` | `/search/synonym-suggestions` | List AI/analytics synonym suggestions |
| `POST` | `/search/synonym-suggestions/generate` | Generate synonym suggestions from retrieval logs |
| `POST` | `/search/synonym-suggestions/{id}/accept` | Accept a suggestion into synonym review |
| `POST` | `/index/sop-version` | Index approved SOP version |
| `POST` | `/delete/sop-version` | Remove version from semantic index |
| `POST` | `/search/semantic` | Semantic search |
| `POST` | `/suggest` | Related SOP and grounded answer suggestion |
| `POST` | `/summarize` | Checklist summary with citation |
| `POST` | `/evaluate-query` | Query normalization and quality signal |

AI responses must include `citations`. If no reliable source exists, the service must return a warning and no fabricated answer.
