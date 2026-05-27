# Evidence-First Ingestion Plan

## Goal

Implement `docs/goals/extraction.md` by adding a shared evidence-first IR around the current ingestion pipeline while preserving existing document-type extractors and API contracts.

## Constraints

- Keep `apps/cs-kb-ai/app/ingestion.py` as the compatibility orchestrator because an `app/ingestion/` package would conflict with the existing module import path.
- Do not remove specialized extractors for PDF, DOCX, XLSX, Markdown, or text.
- Do not publish or index chunks that lack source evidence.
- Preserve existing working behavior and tests.

## Tasks

1. Add a `DocumentEvidenceGraph` IR with artifact, container, source element, relation, semantic unit, and evidence chunk models.
2. Add provenance helpers and adapters from current extractor outputs into the shared IR.
3. Add reasoning stubs/prompts and deterministic observe/adjudicate/verify passes that operate over evidence IDs.
4. Add evidence, workflow, table, spreadsheet, chart, parser-disagreement, and chunk-support validators.
5. Add evidence-bound chunk generation for non-AI fallback paths.
6. Integrate evidence graph build, artifacts, validation, and publish gating into `prepare_document_version`.
7. Add audit/migration documentation.
8. Add tests for evidence-bound fallback chunks, unsupported claims, workflow edge evidence, spreadsheet locators, Markdown line spans, and publish blocking.
9. Run targeted and broader verification before commit/push.

## Verification

- `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest apps.cs-kb-ai.tests...` is invalid because of the hyphenated package path; use discovery/file paths instead.
- Run targeted tests with `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest apps/cs-kb-ai/tests/test_evidence_graph_ingestion.py`.
- Run broader AI service tests with `PYTHONPATH=apps/cs-kb-ai apps/cs-kb-ai/.venv/bin/python -m unittest discover apps/cs-kb-ai/tests`.
