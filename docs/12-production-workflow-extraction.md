# Production Workflow Extraction Gate

This project treats workflow PDFs as draft extractions until CS Ops verifies source trace and Lead publishes the curated version.

## Workflow PDF Contract

For `workflow_diagram` documents, the AI extraction must produce:

- `full_sop`: document-level layer for reading, training, and audit.
- `workflow_graph`: nodes, edges, confidence, and human-review reason.
- `atomic_units`: quick-answer units for retrieval, such as `sla_rule`, `decision_rule`, `escalation_rule`, `case_creation_rule`, `handoff_rule`, `macro_script`, and `operational_note`.
- `source_refs`: source trace per unit. PDF units must at least include `source_file` and `page`.

PDF workflow extraction requires rendered page images. Install AI dependencies with:

```bash
cd apps/cs-kb-ai
.venv/bin/pip install -r requirements.txt
```

If PDF rendering is unavailable, extraction fails recoverably; the upload record remains, but no draft units are published or indexed.

The raw source file is stored per document version in `ai_document_sources` so the review UI can show the rendered source side-by-side with structured units. Current preview endpoint:

```txt
GET /api/v1/ai/versions/:version_id/source/pages/:page_number
```

It returns a JPEG render for PDF sources. Non-PDF sources continue to use raw extracted text/table evidence.

If a PDF unit only has page-level trace and no bbox, it is marked:

```json
{
  "source_ref_quality": "page_only",
  "production_ready_source_refs": false,
  "source_ref_acknowledged": false
}
```

CS Ops must verify and acknowledge those units in the review UI before publish.

## Publish Gate

Publishing is blocked when:

- Full SOP layer is missing.
- Any extraction unit still needs review.
- Owner team is missing.
- Required source refs are missing.
- Workflow graph is missing, unreviewed, low-confidence, or has no edges.
- Page-only PDF source refs are not acknowledged.
- High-risk policy/workflow content has no effective date.

For Chat Social workflows detected by terms like `Chat Social`, `Fanpage`, `Pancake`, `source internal`, or `84912345678`, publishing also requires reviewed units for:

- `sla_rule`
- `decision_rule` or `decision_point`
- `escalation_rule`
- `case_creation_rule`
- `handoff_rule`
- `macro_script`
- `operational_note`

## Lookup Evaluation

After publishing the Chat Social SOP, run:

```bash
cd apps/cs-kb-ai
AI_BASE_URL=http://localhost:8090 .venv/bin/python scripts/evaluate_chat_social.py
```

The script verifies golden queries such as `SLA chat social`, `không có SĐT tạo case social`, `SI OB source internal`, and `QA audit Pancake` return the expected unit types in top-5 retrieval.
