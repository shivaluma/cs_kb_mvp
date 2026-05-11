from __future__ import annotations

import io
import unittest

from docx import Document
from openpyxl import Workbook

from app import ingestion
from app.schemas import DocumentMetadata


class IngestionDegradedDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_rule_extractor = ingestion.extract_rule_table_units
        self.original_workflow_extractor = ingestion.extract_workflow_units
        self.original_renderer = ingestion.render_pdf_pages_as_data_urls

    def tearDown(self) -> None:
        ingestion.extract_rule_table_units = self.original_rule_extractor
        ingestion.extract_workflow_units = self.original_workflow_extractor
        ingestion.render_pdf_pages_as_data_urls = self.original_renderer

    def test_docx_policy_rule_openrouter_disabled_creates_degraded_units(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: ([], ["openrouter_disabled"])
        data = docx_bytes(
            [
                "Quy định khóa/mở khóa tài khoản",
                "1. Trường hợp khóa tài khoản: Nếu tài khoản đang bị khóa vì lý do khác thì L2 kiểm tra trước khi xử lý.",
                "Lưu ý: không cung cấp thông tin bảo mật cho người không được xác minh.",
            ]
        )

        _raw, _digest, chunks, warnings, enrichment = ingestion.prepare_document_version(
            filename="quy-dinh-khoa-mo-khoa.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=data,
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        sections = [chunk["section"] for chunk in chunks]
        self.assertEqual(enrichment["document_type"], "policy_rule")
        self.assertEqual(enrichment["extraction_status"], "degraded")
        self.assertTrue(enrichment["publish_blocked"])
        self.assertIn("full_sop", sections)
        self.assertIn("candidate_rule", sections)
        self.assertIn("candidate_warning", sections)
        self.assertTrue(any("openrouter_disabled" in warning for warning in warnings))
        first_rule = next(chunk for chunk in chunks if chunk["section"] == "candidate_rule")
        self.assertEqual(first_rule["metadata"]["review_status"], "needs_review")
        self.assertEqual(first_rule["metadata"]["source_ref_quality"], "paragraph_only")
        artifacts = enrichment["pipeline_artifacts"]
        self.assertTrue(any(artifact["artifact_type"] == "source_blocks" for artifact in artifacts))
        self.assertTrue(any(artifact["artifact_type"] == "classification_result" for artifact in artifacts))
        self.assertTrue(any(artifact["artifact_type"] == "degraded_draft" for artifact in artifacts))
        self.assertTrue(any(artifact["artifact_type"] == "verification_report" for artifact in artifacts))
        self.assertEqual(enrichment["pipeline_job_status"], "degraded")

    def test_excel_multiple_dated_sheets_creates_candidate_rows_with_scope(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: ([], ["openrouter_invalid_json"])
        data = workbook_bytes(
            {
                "Từ ngày 01.05.2025": [["Case", "Action"], ["A", "Kiểm tra và xử lý theo quy định"]],
                "Old archive": [["Case", "Action"], ["B", "Không tự động active historical row"]],
            }
        )

        _raw, _digest, chunks, _warnings, enrichment = ingestion.prepare_document_version(
            filename="rules.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=data,
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        table_rows = [chunk for chunk in chunks if chunk["section"] == "candidate_table_row"]
        self.assertEqual(enrichment["document_type"], "policy_table")
        self.assertEqual(enrichment["extraction_status"], "degraded")
        self.assertEqual(len(table_rows), 2)
        current = next(chunk for chunk in table_rows if chunk["metadata"]["sheet_name"] == "Từ ngày 01.05.2025")
        historical = next(chunk for chunk in table_rows if chunk["metadata"]["sheet_name"] == "Old archive")
        self.assertEqual(current["metadata"]["effective_from"], "2025-05-01")
        self.assertEqual(current["metadata"]["version_scope"], "current_candidate")
        self.assertEqual(historical["metadata"]["version_scope"], "historical_candidate")
        self.assertEqual(current["metadata"]["source_refs"][0]["row_start"], 2)
        self.assertEqual(current["metadata"]["source_refs"][0]["column_names"], ["Case", "Action"])
        self.assertTrue(any(artifact["artifact_type"] == "structuring_plan" for artifact in enrichment["pipeline_artifacts"]))

    def test_workflow_ai_failure_does_not_create_confirmed_graph(self) -> None:
        classification = type("Classification", (), {"document_type": "workflow_diagram", "source_type": "diagram_pdf", "confidence": 0.78})()
        chunks = ingestion.build_degraded_workflow_draft(
            filename="workflow.pdf",
            raw_text="1. CS tiếp nhận yêu cầu\n2. Nếu đủ thông tin thì xử lý\nLưu ý: SLA 30 phút",
            blocks=[],
            raw_context={},
            classification=classification,
            ai_error="ai_workflow_structuring_failed:invalid_json",
        )

        sections = [chunk.section for chunk in chunks]
        self.assertIn("full_sop", sections)
        self.assertIn("candidate_workflow_text", sections)
        self.assertIn("candidate_step", sections)
        self.assertNotIn("workflow_graph", sections)
        self.assertTrue(all(chunk.metadata["publish_blocked"] for chunk in chunks))
        self.assertEqual(chunks[0].metadata["graph_extraction_status"], "not_reliable_without_layout_review")

    def test_workflow_visual_layout_creates_reviewable_bbox_candidates(self) -> None:
        classification = type("Classification", (), {"document_type": "workflow_diagram", "source_type": "diagram_pdf", "confidence": 0.78})()
        chunks = ingestion.build_degraded_workflow_draft(
            filename="workflow.pdf",
            raw_text="1. CS tiếp nhận yêu cầu",
            blocks=[],
            raw_context={
                "visual_layout": {
                    "summary": {"shape_candidate_count": 1, "edge_candidate_count": 0},
                    "pages": [
                        {
                            "page": 1,
                            "graph_candidate": {
                                "nodes": [
                                    {
                                        "id": "p1_node_1",
                                        "type": "action",
                                        "title": "CS tiếp nhận yêu cầu",
                                        "bbox": [10, 20, 120, 80],
                                    }
                                ],
                                "edge_candidates": [],
                            },
                        }
                    ],
                }
            },
            classification=classification,
            ai_error="ai_workflow_structuring_failed:invalid_json",
        )

        visual_candidate = next(chunk for chunk in chunks if chunk.metadata.get("visual_node_id") == "p1_node_1")
        self.assertEqual(chunks[0].metadata["graph_extraction_status"], "visual_layout_candidates_need_review")
        self.assertEqual(visual_candidate.metadata["source_ref_quality"], "bbox")
        self.assertFalse(visual_candidate.metadata["source_ref_acknowledged"])
        self.assertEqual(visual_candidate.metadata["source_refs"][0]["bbox"], [10, 20, 120, 80])

    def test_workflow_ai_structuring_receives_visual_context(self) -> None:
        captured: dict[str, object] = {}

        def fake_workflow_extractor(_filename: str, _raw_text: str, page_images=None, visual_context=None):
            captured["page_images"] = page_images
            captured["visual_context"] = visual_context
            return [], ["openrouter_disabled"]

        classification = type("Classification", (), {"document_type": "workflow_diagram", "source_type": "diagram_pdf", "confidence": 0.78})()
        original_workflow_extractor = ingestion.extract_workflow_units
        original_render_pdf = ingestion.render_pdf_pages_as_data_urls
        ingestion.extract_workflow_units = fake_workflow_extractor
        ingestion.render_pdf_pages_as_data_urls = lambda _data: (["data:image/jpeg;base64,abc"], ["pdf_vision_pages_rendered:1"])
        try:
            _chunks, warnings, ai_error = ingestion.try_ai_structuring(
                filename="workflow.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
                raw_text="Quy trình có Yes/No",
                classification=classification,
                visual_layout={
                    "source_type": "pdf_visual_layout",
                    "summary": {"shape_candidate_count": 1, "edge_candidate_count": 1},
                    "pages": [
                        {
                            "page": 1,
                            "image_size": [200, 100],
                            "graph_candidate": {
                                "nodes": [{"id": "p1_node_1", "type": "action", "title": "Start", "bbox": [1, 2, 3, 4]}],
                                "edge_candidates": [],
                            },
                        }
                    ],
                },
            )
        finally:
            ingestion.extract_workflow_units = original_workflow_extractor
            ingestion.render_pdf_pages_as_data_urls = original_render_pdf

        self.assertIn("visual_graph_context_supplied_to_llm", warnings)
        self.assertIn("openrouter_disabled", ai_error)
        self.assertIsInstance(captured["visual_context"], dict)
        self.assertEqual(captured["visual_context"]["summary"]["shape_candidate_count"], 1)

    def test_successful_ai_extraction_creates_structured_draft(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: (
            [
                {
                    "unit_type": "full_sop",
                    "title": "Quy định xử lý",
                    "content": "Full SOP content",
                    "confidence": 0.92,
                    "metadata": {"retrieval_scope": "document"},
                    "source_refs": [{"source_type": "docx", "source_file": "policy.docx", "paragraph_index": 0}],
                },
                {
                    "unit_type": "policy_rule",
                    "title": "Kiểm tra điều kiện",
                    "content": "Nếu có điều kiện A thì xử lý theo nguồn.",
                    "confidence": 0.91,
                    "metadata": {},
                    "source_refs": [{"source_type": "docx", "source_file": "policy.docx", "paragraph_index": 1}],
                },
            ],
            [],
        )
        data = docx_bytes(["Quy định xử lý", "Nếu có điều kiện A thì xử lý theo nguồn."])

        _raw, _digest, chunks, _warnings, enrichment = ingestion.prepare_document_version(
            filename="policy.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=data,
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        self.assertEqual(enrichment["extraction_status"], "structured")
        self.assertFalse(enrichment["publish_blocked"])
        self.assertIn("policy_rule", [chunk["section"] for chunk in chunks])
        self.assertTrue(all(chunk["metadata"]["extraction_status"] == "structured" for chunk in chunks))
        self.assertTrue(all(chunk["metadata"]["index_eligible"] is False for chunk in chunks))
        self.assertTrue(any(artifact["artifact_type"] == "ai_structured_payload" for artifact in enrichment["pipeline_artifacts"]))


def docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def workbook_bytes(sheets: dict[str, list[list[str]]]) -> bytes:
    workbook = Workbook()
    first = True
    for sheet_name, rows in sheets.items():
        worksheet = workbook.active if first else workbook.create_sheet()
        first = False
        worksheet.title = sheet_name
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
