# Extraction Pipeline Flow

This document describes the generic ingestion pipeline used by uploaded CS SOP documents. It is intentionally implementation-oriented so reviewers can audit the actual system behavior without reading every source file.

## Generic Flow

Every upload goes through the same outer stages:

1. **Raw evidence extraction**
   - Extract raw text from PDF, DOCX, XLSX, or plain text.
   - Preserve source-specific structure when available:
     - spreadsheet sheets/rows/cells/hyperlinks
     - DOCX paragraphs/tables
     - PDF text lines
   - Output is persisted as `map/source_blocks`.

2. **Document classification**
   - Classify `document_type`, `source_type`, confidence, risk, and review requirement.
   - Main structured document types are:
     - `policy_rule`
     - `policy_table`
     - `workflow_diagram`
     - `kb_index_workbook`
   - Output is persisted as `classify/classification_result`.

3. **Visual mapping, only when needed**
   - For PDF workflow diagrams, render pages and extract visual layout candidates.
   - Persist:
     - `map/visual_layout_blocks`
     - `map/visual_graph_candidates`
   - Build semantic workflow refinement from visual candidates and source blocks.
   - Persist:
     - `workflow_semantic_refine/workflow_semantic_refinement`

4. **Source evidence view**
   - If raw text exists for an AI-structured document type, build a formatted source view for review/debug.
   - Persist:
     - `map/source_evidence_view`
     - `map/source_evidence_ai_breakdown`

5. **AI or deterministic structuring**
   - Branches by `document_type`.
   - Produces reviewable chunks/units, never published content directly.
   - Persist:
     - `ai_structure/ai_structured_payload`
     - `ai_structure/ai_breakdown`

6. **Fallback draft**
   - If structuring returns no usable chunks, create degraded review candidates from deterministic evidence.
   - Persist:
     - `plan/degraded_draft`

7. **Planning and reconciliation**
   - Add structuring plan when the document type needs human curation.
   - Suggest related/duplicate/conflicting SOPs.
   - Persist:
     - `plan/structuring_plan`
     - `reduce/reconcile_suggestions`

8. **Review normalization and refinement**
   - Normalize unit shapes, source refs, metadata, and review status.
   - Ensure a full SOP layer exists.
   - Apply deterministic delivery refinements.
   - Persist:
     - `refine/refinement_report`
     - `refine/draft_units`

9. **Verification and publish gate**
   - Evaluate hard blockers and warnings.
   - For high-risk structured docs, publish requires explicit review.
   - Persist:
     - `verify/verification_report`
     - `verify/publish_readiness_report`

## Branches By Document Type

### Policy Rule / Policy Table

Flow:

1. Try deterministic DOCX table extraction when table structure is present.
2. Append related document chunks detected from spreadsheet or source references.
3. If deterministic extraction is not enough, call AI rule-table extraction.
4. Validate source refs, unit types, and atomic rules.
5. Fall back to degraded review units only if no usable structured chunks exist.

Expected units:

- `full_sop`
- `policy_rule`
- `exception_rule`
- `warning`
- `operational_note`
- `related_document`

### Workflow Diagram

Flow:

1. Render PDF pages to images.
2. Extract visual layout and graph candidates.
3. Build deterministic semantic refinement from visual candidates.
4. Run **Workflow V3 graph primary**:
   - AI transcribes canvas into nodes, arrows, notes, lanes, relations.
   - Deterministic compiler normalizes graph by step code, typed node model, source refs, annotations.
   - Graph repair handles repairable defects before selection:
     - invalid review metadata such as `not decision`
     - duplicate node IDs
     - missing start/end/terminal edges when evidence supports synthesis
     - unattached annotations when a nearest source node can be found
   - Fidelity validator checks coverage, decisions, boundary nodes, source refs, terminal edges, and graph integrity.
   - Persist V3 debug artifacts:
     - `workflow_canvas_transcription`
     - `workflow_graph_draft`
     - `workflow_fidelity_report`
     - `workflow_graph_repair_report`
5. Candidate flow selection scores V3/V2/legacy/semantic candidates by:
   - schema validity
   - repairability
   - source step coverage
   - decision branch coverage
   - terminal edge coverage
   - annotation coverage
   - source ref coverage
   - graph integrity score
   - overall fidelity score
6. If V3 is high-fidelity after deterministic repair, select it without falling back for minor repairable issues.
7. If V3 has unrepairable fidelity blockers, try V2 vision-primary workflow extraction.
8. If V2 does not pass quality/fidelity, try legacy workflow extraction.
9. If legacy does not pass quality/fidelity, use semantic workflow candidates as degraded/review-only draft.

Important governance:

- Human review remains mandatory.
- Graph topology is never auto-published.
- Semantic fallback is review evidence, not high-confidence graph truth.
- `ai_breakdown.selected_flow` identifies the flow that materially produced final chunks.
- V3 artifacts can exist even if final selected flow falls back to V2/legacy/semantic candidates.

Expected workflow units:

- `full_sop`
- `workflow_graph`
- `decision_point`
- `workflow_step`
- `routing_rule`
- `handoff_rule`
- `sla_rule`
- `operational_note`
- `warning`
- `related_document`

### KB Index Workbook

Flow:

1. Preserve workbook sheets, rows, columns, and hyperlinks.
2. Classify known sheets into index purposes.
3. Build `plan/kb_index_plan` with candidates:
   - collections
   - issue router units
   - SOP references
   - tool links
   - action templates
   - relations
   - unresolved targets
4. Convert plan candidates into review chunks.
5. Approved review items materialize later into first-class KB index tables.

Expected units:

- `issue_router_unit`
- `quick_action_rule`
- `sop_reference`
- `tool_link`
- `vip_overlay_rule`
- `product_update_note`
- `related_document`

### Generic / Unknown Text

Flow:

1. Chunk raw text into reviewable sections.
2. Add `full_sop` layer if possible.
3. Mark as review required.
4. Do not feed production retrieval until reviewed/published.

## Debug Artifacts To Check First

For any extraction issue, inspect these artifacts in order:

1. `classify/classification_result`
   - Confirms whether the document took the intended branch.
2. `map/source_blocks`
   - Shows what raw evidence the pipeline saw.
3. `map/visual_graph_candidates`
   - For workflow PDFs, shows detector candidates before AI.
4. `workflow_semantic_refine/workflow_canvas_transcription`
   - For Workflow V3, shows AI canvas transcription before compiler normalization.
5. `workflow_semantic_refine/workflow_graph_draft`
   - Shows normalized graph candidate.
6. `workflow_semantic_refine/workflow_fidelity_report`
   - Shows why V3 passed or failed.
7. `workflow_semantic_refine/workflow_graph_repair_report`
   - Shows deterministic repairs, remaining missing terminal edges, orphan annotations, and unresolved relations.
8. `ai_structure/ai_breakdown`
   - Shows every attempted flow and the final selected flow.
   - `flow_selection_matrix` explains why the selected flow won.
9. `refine/draft_units`
   - Shows the actual units sent to human review.
10. `verify/verification_report`
   - Shows publish blockers.

## Common Failure Modes

- Correct graph draft exists, but final selected flow is fallback.
- Vision model gives ambiguous node IDs such as `0`, causing start/end collisions.
- Visual detector misses diamonds or treats annotations as steps.
- Graph has enough nodes/edges to pass schema but wrong topology semantics.
- Fallback semantic candidates look like noisy `candidate_*` blobs.
- Source refs are present at page level but not at bbox/cell granularity.

## Current Safety Rules

- Draft/degraded/suggested/unresolved content is review-only.
- Production lookup/chat use latest published and approved content only.
- Approved relations can expand retrieval.
- Suggested/unresolved/rejected relations cannot expand production retrieval.
- High-risk workflow diagrams require human topology review.
