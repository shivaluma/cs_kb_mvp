# Workflow Graph Production Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make workflow/flowchart SOPs publish and index only graph-derived, source-cited chunks with explicit topology validation.

**Architecture:** Keep `workflow_v3.py` as the graph compiler and `openrouter.workflow_payload_to_units()` as the graph-derived chunk generator. Harden the downstream gates so failed graph fidelity, missing visual bbox refs, summary-only source evidence, source evidence units, and degraded fallback candidates cannot reach CS-facing publish/search/vector indexes.

**Tech Stack:** Python FastAPI AI service, Go gateway/indexer, Postgres/pgvector, optional Qdrant, Meilisearch, React/Vite admin UI.

---

### Task 1: Audit Existing Workflow Pipeline

**Files:**
- Read: `apps/cs-kb-ai/app/workflow_v3.py`
- Read: `apps/cs-kb-ai/app/openrouter.py`
- Read: `apps/cs-kb-ai/app/ingestion.py`
- Read: `apps/cs-kb-ai/app/repository.py`
- Read: `apps/cs-kb-api/internal/service/store.go`
- Read: `apps/cs-kb-web/src/workspaces/documents-workspace.tsx`

- [x] **Step 1: Map graph extraction**

`workflow_v3.compile_workflow_v3_payload()` normalizes canvas transcription into nodes, edges, annotations, relations, fidelity report, repair report, and `WorkflowExtractionPayload`.

- [x] **Step 2: Map graph chunk generation**

`openrouter.workflow_payload_to_units()` emits `workflow_graph`, then graph-first chunks through `graph_first_workflow_units()` when a workflow graph is present.

- [x] **Step 3: Map publish/index gaps**

`repository.validate_publish_readiness_tx()` blocks many workflow failures, but source refs for workflow chunks currently accept page-only refs, and some graph validation warnings can be cleared by acknowledgement. `qdrant_index_rows_for_version()` and Go `indexAIChunks()` need explicit production-index eligibility guards.

### Task 2: Backend Publish Safety Gate

**Files:**
- Modify: `apps/cs-kb-ai/app/repository.py`
- Test: `apps/cs-kb-ai/tests/test_workflow_publish_readiness.py`

- [x] **Step 1: Add failing tests**

Add tests asserting workflow publish readiness fails when:
- graph validation errors are acknowledged but unresolved;
- workflow graph has zero confirmed edges;
- `workflow_step`, `decision_node`, `decision_branch`, `workflow_path`, `script_block`, or `annotation` lacks page+bbox source refs;
- workflow chunk source text is a generic summary.

- [x] **Step 2: Implement strict graph validation helpers**

Add helpers in `repository.py`:
- `workflow_graph_has_fidelity_errors(metadata)`;
- `workflow_visual_source_ref_failures(unit_type, metadata)`;
- `workflow_summary_only_source_text_failure(unit_type, content, metadata)`.

- [x] **Step 3: Wire helpers into `validate_publish_readiness_tx()`**

For `document_type == "workflow_diagram"`, append stable failure keys and do not allow acknowledgement to clear fidelity blockers such as validation errors, uncertain edges, zero edges, missing branch edges, missing bbox refs, or summary-only source text.

- [x] **Step 4: Verify targeted tests**

Run: `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest apps.cs-kb-ai.tests.test_workflow_publish_readiness`

Expected: all workflow publish readiness tests pass.

### Task 3: Vector Index Eligibility

**Files:**
- Modify: `apps/cs-kb-ai/app/repository.py`
- Test: `apps/cs-kb-ai/tests/test_repository_vector_backend.py`

- [x] **Step 1: Add failing test for Qdrant rows**

Add a test proving `qdrant_index_rows_for_version()` excludes chunks with `publish_blocked=true`, `source_evidence_only=true`, `review_status != approved`, `extraction_status` outside `structured|manually_curated`, and workflow visual chunks without bbox refs.

- [x] **Step 2: Add SQL filters**

Update `qdrant_index_rows_for_version()` with the same production gates used by retrieval: approved, structured/manually_curated, not publish-blocked, not source evidence.

- [x] **Step 3: Verify targeted vector tests**

Run: `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest apps.cs-kb-ai.tests.test_repository_vector_backend`

Expected: vector backend tests pass.

### Task 4: Meilisearch Index Eligibility

**Files:**
- Modify: `apps/cs-kb-api/internal/service/store.go`
- Test: `apps/cs-kb-api/internal/service/store_test.go`

- [x] **Step 1: Add failing unit tests**

Add tests for a pure helper that returns false for source evidence, publish-blocked, needs-review, degraded, failed, raw OCR, and workflow visual chunks without bbox refs.

- [x] **Step 2: Implement helper and filter**

Add `indexableAIChunk(metadata map[string]any) bool` and use it before appending `aiChunkDocument` in `indexAIChunks()`.

- [x] **Step 3: Verify Go tests**

Run: `go test ./internal/...` from `apps/cs-kb-api`.

Expected: Go tests pass.

### Task 5: Regression For Graph-Derived Chunk Contract

**Files:**
- Modify: `apps/cs-kb-ai/tests/test_workflow_diagram_graph_chunks.py`

- [x] **Step 1: Extend existing fixture assertions**

Assert graph-derived production chunk types contain `source_text`, `retrieval_text`, `display_text`, `open_mode=workflow_diagram`, `chunk_type`, and page+bbox source refs.

- [x] **Step 2: Verify graph chunk tests**

Run: `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest apps.cs-kb-ai.tests.test_workflow_diagram_graph_chunks`

Expected: graph chunk tests pass.

### Task 6: Full Verification And Commit

**Files:**
- Commit only files changed for this implementation.
- Leave unrelated dirty files (`DESIGN.md`, `PRODUCT.md`) untouched.

- [x] **Step 1: Run Python tests**

Run: `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest discover apps/cs-kb-ai/tests`

- [x] **Step 2: Run Go tests**

Run: `go test ./internal/...` from `apps/cs-kb-api`.

- [x] **Step 3: Run web tests/build if UI changes**

Skipped: no web files changed in this implementation.

- [ ] **Step 4: Commit and push**

Stage only implementation files, commit with `fix: harden workflow graph publish indexing`, and push `main`.
