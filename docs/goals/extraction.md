You are working inside an existing document ingestion repository.

Goal:
Redesign the current document ingestion architecture to maximize extraction accuracy across PDF, DOC/DOCX, XLS/XLSX/CSV, Markdown, and plain text. You must audit the current implementation first, then implement architecture changes where necessary. Do not limit yourself to small patches if the current architecture prevents correctness.

Current known flow:
- Upload file
- Local/raw extraction first
- Parse blocks and classify document type
- PDF workflow path extracts visual layout and graph candidates
- AI source-evidence formatter runs for selected AI structured document types
- AI structuring has deterministic fast paths before LLM
- Non-AI documents fall back to chunk_text(raw_text)
- AI/local structuring failure creates degraded draft with publish_blocked=true
- Human review happens after extraction and before publish

Known functions/files to inspect:
- ingestion.py
- extract_raw_evidence
- try_ai_structuring
- extract_spreadsheet
- extract_docx_structure
- extract_text
- workflow visual layout stage
- source evidence formatter
- chunk_text
- build source_evidence chunks
- save draft chunks/artifacts
- review/approve/publish gate

Primary requirement:
Replace the current text-centric ingestion pipeline with an evidence-first architecture.

The new architecture must:
1. Preserve specialized extraction per file type.
2. Normalize all extraction outputs into a shared DocumentEvidenceGraph IR.
3. Run reasoning over evidence, not raw text.
4. Require every extracted semantic unit and every published chunk to have source evidence.
5. Detect parser disagreement and low-confidence regions.
6. Block publish when evidence is missing, ambiguous, or contradictory.
7. Support deterministic fast paths, but not at the cost of silent incorrectness.
8. Allow architecture changes, new modules, new schemas, and modified call flow.
9. Preserve existing behavior where tests prove it is correct.
10. Add tests and fixtures for the new correctness gates.

Important design principle:
Generic reasoning should live at the IR, validation, reconciliation, and chunking layers. Do not use one generic extractor for all formats. PDF, DOCX, Excel, Markdown, and text each need specialized extractors because their source semantics differ.

Implement or scaffold the following architecture:

app/
  ingestion/
    orchestrator.py
    router.py
    config.py

  extraction/
    base.py
    pdf/
      pymupdf_extractor.py
      visual_layout_extractor.py
      vector_primitive_extractor.py
      multimodal_layout_parser.py
    docx/
      docx_structure_extractor.py
      ooxml_extractor.py
    xlsx/
      workbook_extractor.py
      formula_graph_extractor.py
      chart_extractor.py
    markdown/
      markdown_ast_extractor.py
    text/
      text_extractor.py

  ir/
    document_evidence_graph.py
    schema.py
    provenance.py
    confidence.py

  reasoning/
    observe.py
    extract.py
    adjudicate.py
    verify.py
    refine.py

  validators/
    base.py
    evidence.py
    table.py
    chart.py
    workflow_graph.py
    spreadsheet.py
    chunk.py

  chunking/
    evidence_bound_chunker.py
    policy_chunker.py
    workflow_chunker.py
    workbook_chunker.py
    markdown_chunker.py

  review/
    review_artifacts.py
    overlay_builder.py

  evals/
    metrics.py
    fixtures/
    golden/

Do not create unnecessary files if an equivalent module already exists. Reuse existing modules where appropriate, but the final code must expose the same conceptual layers.

Define a DocumentEvidenceGraph IR with at least:

DocumentArtifact:
- artifact_id
- sha256
- mime_type
- extension
- original_filename
- parser_versions
- created_at

Container:
- container_id
- kind: document | page | sheet | section | table | figure | diagram | worksheet_region
- parent_id
- page_number
- sheet_name
- bbox
- order_index
- metadata

SourceElement:
- element_id
- kind:
  paragraph | heading | list_item | table | table_row | table_cell |
  spreadsheet_cell | formula | chart | chart_datapoint |
  image | figure | caption | footnote | code_block |
  graph_node | graph_edge | page_header | page_footer | text
- container_id
- text
- html
- value
- formula
- normalized_value
- bbox
- page_number
- sheet_name
- cell_ref
- row_index
- col_index
- style
- confidence
- provenance
- metadata

Relation:
- relation_id
- kind:
  contains | precedes | labels | caption_for | header_for |
  continuation_of | same_entity_as | references |
  formula_depends_on | chart_uses_range | flows_to
- source_id
- target_id
- confidence
- provenance
- metadata

SemanticUnit:
- unit_id
- unit_type:
  policy_rule | policy_table | workflow_step | workflow_edge |
  kb_index_entry | spreadsheet_region | markdown_section |
  generic_fact | unknown
- fields
- source_element_ids
- confidence
- validation_status
- warnings

Chunk:
- chunk_id
- chunk_type
- text
- source_unit_ids
- source_element_ids
- evidence_hash
- confidence
- publish_eligible
- blocked_reasons

Provenance must support:
- parser_name
- parser_version
- extraction_method: deterministic | ocr | visual_ai | llm | external_oracle
- source_locator:
  PDF: page_number + bbox
  DOCX: paragraph/table/cell path and optional rendered bbox
  XLSX: sheet_name + cell/range/chart ref
  MD: AST path and line span
  TXT: line span / char span
- raw_excerpt_hash
- timestamp

Refactor ingestion orchestration:

Old:
  raw_text -> source_blocks -> classify -> optionally AI structure -> chunks

New:
  artifact -> extraction candidates -> DocumentEvidenceGraph -> region classification -> typed reasoning -> reconciliation -> validation -> evidence-bound chunks

Implement an orchestrator roughly like:

def ingest_document(file, *, accuracy_mode="balanced"):
    artifact = inspect_file(file)
    extractors = router.select_extractors(artifact, accuracy_mode)
    candidates = run_extractors(extractors, artifact)
    graph = normalize_candidates_to_graph(candidates)
    profile = observe_document(graph)
    units = extract_semantic_units(graph, profile)
    units = adjudicate_disagreements(units, graph)
    validation = run_validators(graph, units)
    chunks = build_evidence_bound_chunks(graph, units, validation)
    draft = save_draft(graph, units, chunks, validation)
    return draft

Accuracy modes:
- fast: deterministic extractors only, minimal LLM, publish only if validators pass
- balanced: deterministic + AI only for complex/low-confidence regions
- max: deterministic + visual/multimodal + ensemble + verifier pass + conservative publish gate

Critical behavior:
- Non-AI fallback must no longer blindly chunk_text(raw_text) without evidence.
- It may produce text chunks, but each chunk must map to SourceElement IDs and exact locators.
- If locators are not available, mark low confidence and block publish for high-risk document types.
- Optional LLM refinement must never introduce unsupported claims or edges.
- A final verifier must remove or block any content without evidence.

PDF requirements:
- Preserve current local extraction.
- Add or reuse PDF vector primitive extraction for drawings, lines, rectangles, arrows, and image regions.
- For workflow diagrams, build graph candidates from visual primitives before calling AI.
- AI must adjudicate candidates, not invent graph topology from scratch.
- Store graph_node and graph_edge elements with edge-level evidence.
- Add workflow_graph validator:
  node coverage
  edge grounding
  direction check
  branch label check
  dangling edge check
  reachability
  terminal path
  loop evidence
  unknown_edges block publish

Table requirements:
- HTML tables are preferred over Markdown tables.
- Preserve rowspan and colspan.
- Preserve multi-level headers.
- Detect cross-page table continuations.
- Every normalized data cell must know its row header, column header, source bbox/path, and confidence.
- Add table validator:
  cell coverage
  header association
  rowspan/colspan consistency
  continuation consistency
  numeric total consistency where applicable

Chart/data graph requirements:
- Convert charts to tables only when values/labels can be grounded.
- Every chart datapoint must have:
  value
  unit
  series label
  x/category label
  chart title if present
  source bbox or source range
  confidence
- Ambiguous visually estimated values must carry tolerance metadata.
- Do not invent exact values when the chart only supports approximation.

DOCX requirements:
- Preserve paragraph styles, heading levels, list numbering, tables, merged cells, headers, footers, images, captions, footnotes/endnotes/comments where available.
- Use raw OOXML parsing where python-docx does not expose needed structures.
- Optionally render DOCX pages when visual layout is needed, but do not discard OOXML semantics.
- Tables must normalize into table/table_row/table_cell elements with source paths.

XLSX/Excel requirements:
- Treat Excel as a workbook graph, not text.
- Preserve sheets, cells, formulas, cached values, number formats, styles, merged ranges, named ranges, hidden rows/columns, tables, charts, images, comments, and data validations where available.
- Build formula_depends_on relations for parseable formulas.
- Build chart_uses_range relations where chart source ranges can be resolved.
- Chunk by sheet region, table object, named range, chart, or formula dependency cluster, not by raw text.
- If formula result cannot be verified, preserve both formula and cached value and mark confidence appropriately.

Markdown requirements:
- Parse into AST.
- Preserve headings, hierarchy, lists, tables, code fences, links, images, blockquotes, footnotes, and frontmatter.
- Chunk by AST section hierarchy and source line spans.
- Do not use naive character chunking unless AST parsing fails, and then mark degraded.

Reasoning prompts:
Create prompts for these passes, but keep prompts separate from orchestration code:

1. observe_document prompt:
Input: compact summary of DocumentEvidenceGraph elements and relations.
Output JSON:
{
  "document_profile": {
    "primary_type": "...",
    "secondary_types": [],
    "confidence": 0.0
  },
  "regions": [
    {
      "region_id": "...",
      "kind": "policy_table|workflow_diagram|kb_index|spreadsheet_region|markdown_section|generic_text|chart|unknown",
      "container_ids": [],
      "source_element_ids": [],
      "confidence": 0.0,
      "warnings": []
    }
  ]
}

Rules:
- Do not create regions without source_element_ids.
- Use unknown if evidence is insufficient.
- Output JSON only.

2. extract_semantic_units prompt:
Input: region-specific evidence elements only.
Output JSON semantic units.
Rules:
- Every field must cite source_element_ids.
- Do not infer missing policy rules, graph edges, table cells, or spreadsheet values.
- Put ambiguous content in warnings.
- Output JSON only.

3. adjudicate_disagreements prompt:
Input: competing candidates from local parser, visual parser, OCR, VLM parser, and external oracle if present.
Rules:
- Prefer deterministic source semantics for DOCX/XLSX/MD.
- Prefer visual evidence for PDF layout/table/diagram conflicts.
- Prefer explicit formula/cell references over natural language guesses.
- If candidates conflict and evidence does not resolve it, mark unresolved and block publish.
- Output JSON only.

4. verify_units prompt:
Input: semantic units and their cited source elements.
Rules:
- Reject any field without evidence.
- Reject unsupported graph edges.
- Reject table cells without header mapping when used for policy/financial/business logic.
- Reject chart datapoints without labels.
- Reject spreadsheet facts without cell/range support.
- Output corrected JSON and validation warnings only.

Validators:
Implement deterministic validators before and after LLM verification:
- evidence_coverage_validator
- unsupported_claim_validator
- table_structure_validator
- chart_datapoint_validator
- workflow_graph_validator
- spreadsheet_semantics_validator
- chunk_support_validator
- parser_disagreement_validator

Publish gate:
A chunk is publish eligible only if:
- publish_eligible == true
- source_element_ids non-empty
- evidence_hash present
- validation_status == passed
- confidence >= configured threshold
- no critical warnings
- no unresolved parser disagreement
- no unknown_edges for workflow chunks
- no unsupported claims

Human review:
Create review artifacts for low-confidence regions:
- parsed markdown/html
- source evidence list
- overlay data for PDF pages where bbox exists
- table reconstruction preview
- workflow graph overlay
- spreadsheet region summary
- blocked reasons
- repair instructions

Tests:
Add or update tests for:
1. Non-AI fallback chunks still have source evidence.
2. AI refinement cannot add unsupported fields.
3. Table with merged headers preserves rowspan/colspan.
4. Cross-page table continuation is represented as continuation_of.
5. Workflow graph edge must have edge evidence.
6. XLSX formula cell preserves formula and cached value separately.
7. Spreadsheet chunk cites sheet/cell/range locators.
8. Markdown chunks preserve AST heading hierarchy and line spans.
9. Parser disagreement causes publish_blocked=true.
10. Degraded drafts are saved but not publish eligible.
11. Existing deterministic fast paths still work.
12. Published search/chat only uses approved/published/current chunks.

Implementation strategy:
- First audit current code and write a short architecture report in docs/ingestion_accuracy_audit.md.
- Then implement minimal viable DocumentEvidenceGraph and adapters around current extractors.
- Refactor ingestion.py to call the new orchestrator while keeping a compatibility wrapper if needed.
- Add validators and enforce the publish gate.
- Add tests.
- Do not remove existing working logic unless replaced by tested equivalent.
- Keep changes incremental but architecture-correct.
- Prefer typed dataclasses or Pydantic models for IR schemas.
- Ensure serialization to JSON for saved artifacts.
- Include parser version metadata for every extraction candidate.
- Make failure modes explicit and testable.

Acceptance criteria:
- Running tests passes.
- Current ingestion still works for existing supported document types.
- Every draft chunk has source_element_ids and evidence_hash.
- No published chunk can be created without evidence.
- Workflow graph chunks require edge-level evidence.
- Excel chunks cite sheet/cell/range.
- Markdown chunks cite AST path or line span.
- Low-confidence or unresolved documents create degraded drafts with publish_blocked=true.
- The architecture allows adding external parsers without changing downstream reasoning.
- The code clearly separates extraction, IR normalization, reasoning, validation, chunking, and review artifacts.

After implementation:
- Provide a summary of changed files.
- Provide migration notes from old ingestion.py flow to new orchestrator.
- Provide remaining risks and TODOs.
