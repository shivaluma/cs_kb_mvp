# 06. Implementation Roadmap

## Phase 0: Discovery and Data Audit

Deliverables:

- Audit existing SOP Excel/email sources.
- Define final taxonomy and migration template.
- Identify required fields and missing content.
- Select pilot SOP category.

Exit criteria:

- Migration template approved.
- SOP schema approved.
- Role matrix approved.

## Phase 1: Core SOP Website

Deliverables:

- React frontend.
- Go API.
- Postgres schema.
- SOP CRUD.
- Version workflow.
- Keyword search.
- Homepage.
- Analytics logging.
- Excel import tool.

Exit criteria:

- At least 95% pilot SOPs migrated.
- Search accuracy reaches at least 85% on test query set.
- Agent can find SOP from homepage/search.
- Lead can publish a new version.
- Audit logs are available.

## Phase 2: AI Search Enhancement

Deliverables:

- Python AI service.
- Chunking pipeline.
- Embeddings.
- Semantic search.
- AI suggested SOP.
- AI summary with citations.
- AI feedback/rating.
- Guardrails.

Exit criteria:

- AI suggestion rating reaches at least 4/5.
- 100% AI answers cite SOP/version.
- No serious misinformation in pilot.
- AI failure does not break normal search/read.

## Build Order

1. Structured SOP schema.
2. Version control.
3. Keyword search, tags, and filters.
4. Analytics logging.
5. Migration from Excel.
6. AI semantic search.
7. AI suggestions with citations.
