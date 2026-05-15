# Production Workflow Extraction Gate

This project treats workflow PDFs as draft extractions until CS Ops verifies source trace and Lead publishes the curated version.

## Workflow PDF Contract

For `workflow_diagram` documents, the AI extraction must produce:

- `full_sop`: document-level layer for reading, training, and audit.
- `workflow_graph`: nodes, edges, confidence, and human-review reason.
- `atomic_units`: quick-answer units for retrieval, such as `sla_rule`, `decision_rule`, `escalation_rule`, `case_creation_rule`, `handoff_rule`, `macro_script`, and `operational_note`.
- `source_refs`: source trace per unit. PDF units must at least include `source_file` and `page`.

Workflow PDFs use `ai_direct_visual_extraction` mode:

- rendered page images are the source of truth
- OCR/parser text is hint-only evidence
- graph edges must come from visible arrows/connectors or visual graph candidates
- OCR line order must not create workflow topology
- unclear topology must be represented as `uncertain_edges`, warnings, and review reasons

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

If the pipeline has to synthesize a fallback source ref, it is marked:

```json
{
  "source_ref_synthetic": true,
  "source_ref_quality": "synthetic_missing"
}
```

Synthetic refs never count as valid grounding. `verify/source_grounding_validator` marks those units as `needs_review`, sets `publish_blocked=true`, and blocks publish readiness.

## Publish Gate

Publishing is blocked when:

- Full SOP layer is missing.
- Any extraction unit still needs review.
- Owner team is missing.
- Required source refs are missing.
- Any source ref is synthetic, missing source file/type, or inappropriate for the source document family.
- Workflow graph is missing, unreviewed, low-confidence, or has no edges.
- Page-only PDF source refs are not acknowledged.
- High-risk policy/workflow content has no effective date.

For workflow documents, the AI extraction may return `document_metadata.required_unit_types` or `publish_readiness.required_unit_types`. Publishing also requires reviewed units for every required type declared by the extraction. Typical workflow unit types include:

- `sla_rule`
- `decision_rule` or `decision_point`
- `escalation_rule`
- `case_creation_rule`
- `handoff_rule`
- `macro_script`
- `operational_note`

## Lookup Evaluation

After publishing a workflow SOP, create a small golden query set that matches the document's extracted unit types and run retrieval evaluation against the published version only. Example evaluator scripts should assert:

- Each golden query returns the expected `unit_type` in top-5.
- Result citations point to the published SOP version and source page/sheet/row.
- Draft, archived, and failed extraction units are not returned.
- Candidate, degraded, unreviewed, publish-blocked, and synthetic-source units are not returned.
