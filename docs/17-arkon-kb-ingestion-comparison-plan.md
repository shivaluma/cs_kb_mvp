# Arkon KB Ingestion Comparison Plan

This note records the Arkon review and how the CS KB pipeline is being upgraded from it. It is intentionally implementation-facing: every item should map to code, schema, or an operator workflow.

## Arkon Pattern

Arkon treats uploaded knowledge as a staged compilation pipeline:

1. Persist source files before extraction.
2. Run durable map work over source units.
3. Produce a reviewable compilation plan.
4. Reduce and reconcile mapped facts before creating wiki pages.
5. Store generated pages as a retrieval layer.
6. Keep embeddings and search scoped to the compiled knowledge surface.
7. Preserve image assets and captions so visual evidence is not lost.

The strongest idea is not any single parser. It is the separation between raw evidence, map outputs, reduce/reconcile decisions, and compiled pages.

## CS KB Baseline

CS KB already had stronger evidence governance than Arkon in several areas:

- structured source refs for DOCX, XLSX, PDF, and workflow diagrams
- evidence-bound chunks and source hashes
- draft/review/publish lifecycle gates
- hybrid retrieval over chunk-level policy units
- workflow graph validation and source-parent display context

The weak spots were mostly pipeline durability and compiled knowledge layers:

- MAP outputs were artifacts, not first-class retryable rows
- compilation plans were not independently reviewable
- reduce/reconcile suggestions were not persisted as workflow objects
- document-level compiled pages were not searchable as broad context
- embedding specs existed only implicitly in chunk metadata
- image uploads and embedded images were not captioned or represented consistently

## Implemented Upgrade Track

The current implementation adds the Arkon ideas without replacing CS KB's evidence-first model.

1. Durable map rows
   - `map_unit_extracts` is emitted during ingestion.
   - `extraction_map_unit_outputs` persists each unit with status, attempts, source refs, source element IDs, evidence hash, and retry metadata.
   - `PATCH /ai/v1/extraction-map-units/{job_id}/{unit_id}` updates retry/status state.

2. Reviewable compilation plans
   - `document_compilation_plan` is emitted from chunk and source coverage data.
   - `extraction_compilation_plans` stores the plan, operation count, coverage, gates, approval state, and rejection/error state.
   - `PATCH /ai/v1/extraction-compilation-plans/{plan_id}` approves or rejects a plan.

3. Reduce/reconcile layer
   - `extraction_reduce_items` persists deduped claims from map output.
   - Reconcile suggestions compare title/metadata overlap against existing documents.
   - `reduce_reconcile_verification` promotes conflicting policy units into publish-readiness blockers.
   - `GET /ai/v1/versions/{version_id}/reduce-reconcile/report` and `.md` summarize duplicate claims, duplicate titles, related SOPs, and conflicts for operators.

4. Compiled page retrieval
   - `ai_compiled_pages` stores document-overview pages compiled from `full_sop`.
   - Compiled pages copy the `full_sop` embedding and source chunk indexes.
   - Retrieval can opt into compiled pages with `include_compiled_pages`.
   - Qdrant indexing marks `retrieval_layer=compiled_page` so normal chunk retrieval does not silently mix broad document context into atomic policy search.
   - Approved compilation plans can now materialize wiki-style compiled pages grouped by unit type, with `unit_type=compiled_wiki_page`.

5. Embedding model governance
   - `embedding_model_specs` records provider/model/dimension specs.
   - `embedding_migration_jobs` records migration plans and batch progress.
   - `POST /ai/v1/embedding/migration-plan` creates a migration job.
   - `POST /ai/v1/embedding/migration-jobs/{job_id}/run` re-embeds stale chunks and compiled pages in batches.
   - `scripts/run_embedding_migrations.py` lets operators or schedulers drain pending migration jobs without going through the API.
   - Admin reset/vector schema reset now rebuilds both `ai_chunks.embedding` and `ai_compiled_pages.embedding` for the active embedding dimension.

6. Image evidence
   - Direct image uploads become `image_asset` source elements.
   - OpenRouter vision captioning can produce `image_caption` elements.
   - DOCX `word/media/*` images are extracted into `embedded_images`.
   - Embedded DOCX image bytes are passed transiently to the captioner when under the safety size limit, then stripped before raw context is persisted.
   - Embedded images become caption-ready evidence nodes with source refs and describe relations when captions exist.

## Retrieval Flow After Upgrade

Default retrieval remains atomic and evidence-first:

1. Query is normalized and expanded with governed synonyms.
2. Lexical and vector search pull published, approved, structured chunk rows.
3. Qdrant/pgvector filters exclude compiled pages by default.
4. Ranking selects source-grounded chunks.
5. Display context hydrates source parent and citation metadata.

Broad document context is explicit:

1. Client sets `include_compiled_pages=true`.
2. Retrieval adds compiled-page vector candidates.
3. Compiled-page rows carry `unit_type=compiled_document_overview` and `retrieval_layer=compiled_page`.
4. Results remain traceable to source chunk indexes and unit types.

## Remaining Hardening Backlog

These are next-phase items, not prerequisites for the current backend path:

1. Add frontend controls for map-unit retry/status and compilation-plan review.
