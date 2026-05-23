from __future__ import annotations

import unittest

from app.chunking.evidence_bound_chunker import build_evidence_bound_chunks, legacy_chunks_from_evidence
from app.ingestion import parse_document_blocks, prepare_document_version
from app.ir.document_evidence_graph import build_document_evidence_graph
from app.ir.schema import SemanticUnit
from app.schemas import DocumentMetadata
from app.validators.chunk_support import validate_chunks_supported
from app.validators.evidence import validate_semantic_units_supported
from app.validators.workflow_graph import validate_workflow_graph


class EvidenceGraphIngestionTest(unittest.TestCase):
    def test_text_evidence_graph_preserves_line_source_elements(self) -> None:
        raw_text = "Greeting SOP\nCS greets the customer.\nCS confirms the issue."
        blocks = parse_document_blocks("greeting.txt", "text/plain", raw_text, {})

        graph = build_document_evidence_graph(
            filename="greeting.txt",
            content_type="text/plain",
            data=raw_text.encode("utf-8"),
            raw_text=raw_text,
            raw_context={},
            blocks=blocks,
            classification=None,
        )

        text_elements = [element for element in graph.source_elements if element.kind == "text"]
        self.assertEqual(len(text_elements), 3)
        self.assertEqual(text_elements[0].provenance.source_locator["line_start"], 1)
        self.assertEqual(text_elements[2].provenance.source_locator["line_end"], 3)
        self.assertTrue(text_elements[0].provenance.raw_excerpt_hash)

    def test_non_ai_fallback_chunks_are_evidence_bound(self) -> None:
        raw_text = "Greeting SOP\nCS greets the customer.\nCS confirms the issue."
        _raw, _digest, chunks, _warnings, enrichment = prepare_document_version(
            filename="greeting.txt",
            content_type="text/plain",
            data=raw_text.encode("utf-8"),
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        self.assertEqual(enrichment["document_type"], "text_sop")
        self.assertIn("document_evidence_graph", {artifact["artifact_type"] for artifact in enrichment["pipeline_artifacts"]})
        draft_chunks = [chunk for chunk in chunks if chunk["metadata"].get("unit_type") != "source_evidence_section"]
        self.assertTrue(draft_chunks)
        for chunk in draft_chunks:
            metadata = chunk["metadata"]
            self.assertTrue(metadata.get("source_element_ids"), chunk)
            self.assertTrue(metadata.get("evidence_hash"), chunk)
            self.assertTrue(metadata.get("source_refs"), chunk)

    def test_unsupported_semantic_unit_is_blocked(self) -> None:
        unit = SemanticUnit(
            unit_id="unit_missing",
            unit_type="generic_fact",
            fields={"content": "Unsupported claim"},
            source_element_ids=[],
            confidence=0.91,
        )

        result = validate_semantic_units_supported([unit])

        self.assertFalse(result.passed)
        self.assertIn("unit_missing:missing_source_elements", result.critical_warnings)

    def test_workflow_edge_requires_edge_level_evidence(self) -> None:
        graph = build_document_evidence_graph(
            filename="flow.pdf",
            content_type="application/pdf",
            data=b"%PDF",
            raw_text="",
            raw_context={
                "visual_layout": {
                    "pages": [
                        {
                            "page": 1,
                            "image_size": [1000, 1000],
                            "graph_candidate": {
                                "nodes": [
                                    {"id": "step_1", "text": "1 Start", "bbox": [1, 1, 10, 10]},
                                    {"id": "step_2", "text": "2 End", "bbox": [20, 20, 30, 30]},
                                ],
                                "edges": [
                                    {"from_node": "step_1", "to_node": "step_2", "condition": "next"},
                                ],
                            },
                        }
                    ]
                }
            },
            blocks=[],
            classification=None,
        )

        result = validate_workflow_graph(graph)

        self.assertFalse(result.passed)
        self.assertIn("workflow_edge_missing_source_ref", result.critical_warnings)

    def test_spreadsheet_chunks_cite_sheet_cell_locator(self) -> None:
        graph = build_document_evidence_graph(
            filename="rules.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=b"fake",
            raw_text="# Rules\nA1: Refund policy",
            raw_context={"sheets": [("Rules", [(1, ["Policy", "Refund"]), (2, ["Action", "Review payment"])])]},
            blocks=[],
            classification=None,
        )
        chunks = legacy_chunks_from_evidence(graph, document_type="policy_table", source_type="spreadsheet")

        self.assertTrue(chunks)
        for chunk in chunks:
            refs = chunk.metadata.get("source_refs") or []
            self.assertTrue(any(ref.get("sheet") == "Rules" and ref.get("row_start") for ref in refs), chunk)
            self.assertTrue(chunk.metadata.get("source_element_ids"))
            self.assertTrue(chunk.metadata.get("evidence_hash"))

    def test_markdown_evidence_preserves_heading_hierarchy_and_line_spans(self) -> None:
        raw_text = "# Policy\n\n## Refund\nCS checks payment.\n"
        blocks = parse_document_blocks("policy.md", "text/markdown", raw_text, {})
        graph = build_document_evidence_graph(
            filename="policy.md",
            content_type="text/markdown",
            data=raw_text.encode("utf-8"),
            raw_text=raw_text,
            raw_context={},
            blocks=blocks,
            classification=None,
        )

        markdown_elements = [element for element in graph.source_elements if element.metadata.get("ast_path")]
        self.assertTrue(markdown_elements)
        self.assertTrue(any(element.provenance.source_locator.get("line_start") == 3 for element in markdown_elements))
        self.assertTrue(any(element.metadata.get("section_path") == ["Policy", "Refund"] for element in markdown_elements))

    def test_chunk_support_validator_blocks_missing_evidence_hash(self) -> None:
        result = validate_chunks_supported(
            build_evidence_bound_chunks(
                graph=None,
                semantic_units=[
                    SemanticUnit(
                        unit_id="unit_1",
                        unit_type="generic_fact",
                        fields={"content": "No source"},
                        source_element_ids=[],
                    )
                ],
            )
        )

        self.assertFalse(result.passed)
        self.assertIn("unit_1:missing_source_elements", result.critical_warnings)


if __name__ == "__main__":
    unittest.main()
