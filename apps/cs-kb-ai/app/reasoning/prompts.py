OBSERVE_DOCUMENT_PROMPT = """Input: compact summary of DocumentEvidenceGraph elements and relations.
Output JSON:
{
  "document_profile": {"primary_type": "...", "secondary_types": [], "confidence": 0.0},
  "regions": [{"region_id": "...", "kind": "...", "container_ids": [], "source_element_ids": [], "confidence": 0.0, "warnings": []}]
}
Rules:
- Do not create regions without source_element_ids.
- Use unknown if evidence is insufficient.
- Output JSON only.
"""

EXTRACT_SEMANTIC_UNITS_PROMPT = """Input: region-specific evidence elements only.
Output JSON semantic units.
Rules:
- Every field must cite source_element_ids.
- Do not infer missing policy rules, graph edges, table cells, or spreadsheet values.
- Put ambiguous content in warnings.
- Output JSON only.
"""

ADJUDICATE_DISAGREEMENTS_PROMPT = """Input: competing candidates from local parser, visual parser, OCR, VLM parser, and external oracle if present.
Rules:
- Prefer deterministic source semantics for DOCX/XLSX/MD.
- Prefer visual evidence for PDF layout/table/diagram conflicts.
- Prefer explicit formula/cell references over natural language guesses.
- If candidates conflict and evidence does not resolve it, mark unresolved and block publish.
- Output JSON only.
"""

VERIFY_UNITS_PROMPT = """Input: semantic units and their cited source elements.
Rules:
- Reject any field without evidence.
- Reject unsupported graph edges.
- Reject table cells without header mapping when used for policy/financial/business logic.
- Reject chart datapoints without labels.
- Reject spreadsheet facts without cell/range support.
- Output corrected JSON and validation warnings only.
"""
