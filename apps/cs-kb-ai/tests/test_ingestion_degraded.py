from __future__ import annotations

import io
import unittest

from docx import Document
from openpyxl import Workbook

from app import ingestion
from app.schemas import DocumentMetadata, ExtractedUnitsPayload


class IngestionDegradedDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_rule_extractor = ingestion.extract_rule_table_units
        self.original_workflow_extractor = ingestion.extract_workflow_units
        self.original_renderer = ingestion.render_pdf_pages_as_data_urls
        self.original_refiner = ingestion.refine_extracted_units

    def tearDown(self) -> None:
        ingestion.extract_rule_table_units = self.original_rule_extractor
        ingestion.extract_workflow_units = self.original_workflow_extractor
        ingestion.render_pdf_pages_as_data_urls = self.original_renderer
        ingestion.refine_extracted_units = self.original_refiner

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

    def test_degraded_policy_text_does_not_duplicate_warning_clone_content(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: ([], ["openrouter_invalid_json"])

        _raw, _digest, chunks, _warnings, enrichment = ingestion.prepare_document_version(
            filename="Quy định xác minh địa chỉ email.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=docx_email_verification_bytes(),
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        self.assertEqual(enrichment["extraction_status"], "degraded")
        atomic_contents = [
            ingestion.content_fingerprint(chunk["content"])
            for chunk in chunks
            if chunk["metadata"].get("unit_type") != "full_sop"
        ]
        self.assertEqual(len(atomic_contents), len(set(atomic_contents)))
        duplicated_title_units = [
            chunk for chunk in chunks
            if chunk["heading"] == "Quy định xác minh địa chỉ email"
            and chunk["metadata"].get("unit_type") in {"candidate_rule", "candidate_warning"}
        ]
        self.assertLessEqual(len(duplicated_title_units), 1)

    def test_unknown_llm_unit_type_is_normalized_before_validation(self) -> None:
        payload = ExtractedUnitsPayload.model_validate(
            {
                "units": [
                    {
                        "unit_type": "procedure_step",
                        "title": "Kiểm tra email",
                        "content": "CS kiểm tra email trên hệ thống.",
                        "source_refs": [{"source_type": "docx", "source_file": "email.docx", "paragraph_index": 1}],
                    }
                ]
            }
        )

        self.assertEqual(payload.units[0].unit_type, "operational_instruction")
        self.assertEqual(payload.units[0].metadata["original_unit_type"], "procedure_step")

    def test_docx_policy_table_creates_table_aware_atomic_units(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: self.fail("docx policy table should not call OpenRouter")
        data = docx_policy_table_bytes()

        _raw, _digest, chunks, _warnings, enrichment = ingestion.prepare_document_version(
            filename="Quy định làm tròn số tiền.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=data,
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        self.assertEqual(enrichment["document_type"], "policy_rule")
        self.assertEqual(enrichment["extraction_status"], "structured")
        unit_types = [chunk["metadata"]["unit_type"] for chunk in chunks]
        self.assertIn("full_sop", unit_types)
        self.assertGreaterEqual(unit_types.count("policy_rule"), 2)
        self.assertGreaterEqual(unit_types.count("exception_rule"), 2)

        befood_rule = next(chunk for chunk in chunks if chunk["heading"] == "beFood - Bồi hoàn liên quan món ăn")
        self.assertEqual(befood_rule["metadata"]["source_ref_quality"], "table_row")
        self.assertEqual(befood_rule["metadata"]["source_refs"][0]["source_type"], "docx_table")
        self.assertEqual(befood_rule["metadata"]["rounding_threshold"], 500)
        self.assertEqual(len(befood_rule["metadata"]["examples"]), 3)
        self.assertIn("10,450đ -> 10,000đ", befood_rule["content"])

        normal_refund = next(chunk for chunk in chunks if chunk["heading"] == "Dịch vụ khác - Hoàn / rút tiền thông thường")
        self.assertEqual(normal_refund["metadata"]["rounding_threshold"], 300)
        self.assertIn(">300", normal_refund["content"])

        pm04 = next(chunk for chunk in chunks if "PM04" in chunk["heading"])
        self.assertEqual(pm04["metadata"]["unit_type"], "exception_rule")
        self.assertFalse(pm04["metadata"]["rounding_applies"])

        source_blocks = next(artifact for artifact in enrichment["pipeline_artifacts"] if artifact["artifact_type"] == "source_blocks")
        self.assertEqual(source_blocks["payload"]["source_ref_quality"], "table_row")
        self.assertTrue(any(block["type"] == "docx_table_row" for block in source_blocks["payload"]["preview_blocks"]))
        verification = next(artifact for artifact in enrichment["pipeline_artifacts"] if artifact["artifact_type"] == "verification_report")
        self.assertNotIn("missing_atomic_units", verification["payload"]["hard_blockers"])
        self.assertNotIn("degraded_units_require_manual_curation", verification["payload"]["hard_blockers"])

    def test_llm_refine_can_enrich_structured_units_after_extraction(self) -> None:
        ingestion.extract_rule_table_units = lambda _filename, _raw_text: self.fail("docx policy table should not call OpenRouter")

        def fake_refiner(**kwargs):
            refined = []
            for unit in kwargs["units"]:
                metadata = dict(unit.get("metadata") or {})
                metadata["llm_refined"] = True
                metadata["aliases"] = [*metadata.get("aliases", []), "refined lookup alias"]
                refined.append({**unit, "metadata": metadata, "source_refs": unit.get("source_refs") or metadata.get("source_refs")})
            return refined, {"llm_refine_status": "completed", "coverage": {"source": "fake"}}, ["openrouter_refine_used"]

        ingestion.refine_extracted_units = fake_refiner

        _raw, _digest, chunks, warnings, enrichment = ingestion.prepare_document_version(
            filename="Quy định làm tròn số tiền.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=docx_policy_table_bytes(),
            metadata=DocumentMetadata(owner_team="CS Ops"),
        )

        self.assertIn("openrouter_refine_used", warnings)
        self.assertTrue(all(chunk["metadata"].get("llm_refined") is True for chunk in chunks))
        self.assertTrue(any("refined lookup alias" in chunk["metadata"].get("aliases", []) for chunk in chunks))
        refinement = next(artifact for artifact in enrichment["pipeline_artifacts"] if artifact["artifact_type"] == "refinement_report")
        self.assertEqual(refinement["payload"]["llm"]["llm_refine_status"], "completed")
        self.assertIn("post_guard", refinement["payload"]["llm"])

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

    def test_workflow_ai_missing_required_layers_is_not_structured_success(self) -> None:
        def fake_workflow_extractor(_filename: str, _raw_text: str, page_images=None, visual_context=None):
            return (
                [
                    {
                        "unit_type": "full_sop",
                        "title": "Quy trình cần review",
                        "content": "Model không trả full_sop. Backend giữ bản nháp này để CS Ops review lại từ source.",
                        "confidence": 0.45,
                        "metadata": {"retrieval_scope": "document"},
                    },
                    {
                        "unit_type": "workflow_graph",
                        "title": "Quy trình cần review",
                        "content": "Workflow graph tối thiểu.",
                        "confidence": 0.25,
                        "metadata": {"retrieval_scope": "graph", "workflow_graph": {"nodes": [], "edges": []}},
                    },
                ],
                [
                    "full_sop_missing_from_model_synthesized_for_review",
                    "workflow_graph_missing_from_model_synthesized_for_review",
                ],
            )

        classification = type("Classification", (), {"document_type": "workflow_diagram", "source_type": "diagram_pdf", "confidence": 0.78})()
        ingestion.extract_workflow_units = fake_workflow_extractor
        ingestion.render_pdf_pages_as_data_urls = lambda _data: (["data:image/jpeg;base64,abc"], [])

        chunks, warnings, ai_error = ingestion.try_ai_structuring(
            filename="workflow.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.4",
            raw_text="1. CS tiếp nhận yêu cầu\n2. Nếu đủ thông tin thì xử lý",
            classification=classification,
            visual_layout={},
        )

        self.assertEqual(chunks, [])
        self.assertIn("full_sop_missing_from_model_synthesized_for_review", warnings)
        self.assertIn("workflow_graph_missing_from_model_synthesized_for_review", ai_error)

    def test_workflow_ai_without_atomic_units_is_not_structured_success(self) -> None:
        classification = type("Classification", (), {"document_type": "workflow_diagram", "source_type": "diagram_pdf", "confidence": 0.78})()

        def fake_workflow_extractor(_filename: str, _raw_text: str, page_images=None, visual_context=None):
            return (
                [
                    {
                        "unit_type": "full_sop",
                        "title": "Quy trình",
                        "content": "Nội dung tổng quan.",
                        "confidence": 0.8,
                        "metadata": {"retrieval_scope": "document"},
                    },
                    {
                        "unit_type": "workflow_graph",
                        "title": "Quy trình",
                        "content": "Graph có node.",
                        "confidence": 0.75,
                        "metadata": {"retrieval_scope": "graph", "workflow_graph": {"nodes": [{"id": "start"}], "edges": []}},
                    },
                ],
                [],
            )

        ingestion.extract_workflow_units = fake_workflow_extractor
        ingestion.render_pdf_pages_as_data_urls = lambda _data: (["data:image/jpeg;base64,abc"], [])
        chunks, warnings, ai_error = ingestion.try_ai_structuring(
            filename="workflow.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.4",
            raw_text="1. CS tiếp nhận yêu cầu",
            classification=classification,
            visual_layout={},
        )

        self.assertEqual(chunks, [])
        self.assertEqual(warnings, [])
        self.assertIn("missing_atomic_workflow_units", ai_error)

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


def docx_policy_table_bytes() -> bytes:
    document = Document()
    document.add_paragraph("QUY ĐỊNH LÀM TRÒN SỐ TIỀN")
    headers = ["Dịch vụ", "Trường hợp", "Quy tắc làm tròn", "Lưu ý"]
    rows = [
        [
            "beFood",
            "Bồi hoàn liên quan món ăn",
            "Mốc 500đ: <500↓, ≥500↑",
            "Làm tròn giá trị bồi hoàn cuối cùng\nví dụ:\n10,450đ -> 10,000 đ\n10,500đ (hoặc 10,560đ) -> 11,000 đ",
        ],
        ["beFood", "Các trường hợp khác (begin-end...)", "Không áp dụng", "Làm tròn giá trị bồi hoàn cuối cùng"],
        [
            "Dịch vụ khác",
            "Hoàn / rút tiền thông thường",
            "Mốc: 300đ: >300↑, ≤300↓",
            "Tại mỗi bước tính tiền, sau khi tính ra số tiền CS cần phải làm tròn theo quy tắc trước khi thực hiện bước tiếp theo.\nVD:\n10,400 -> 11000\n10,200 -> 10,000",
        ],
        ["Dịch vụ khác", "Hoàn / rút chiết khấu ĐT", "Không áp dụng", "Tại mỗi bước tính tiền, sau khi tính ra số tiền CS cần phải làm tròn theo quy tắc trước khi thực hiện bước tiếp theo."],
        ["Dịch vụ khác", "Hoàn KH về PTTT đã dùng (PM04)", "Không áp dụng", "Tại mỗi bước tính tiền, sau khi tính ra số tiền CS cần phải làm tròn theo quy tắc trước khi thực hiện bước tiếp theo."],
    ]
    table = document.add_table(rows=1, cols=len(headers))
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def docx_email_verification_bytes() -> bytes:
    return docx_bytes(
        [
            "Quy định xác minh địa chỉ email",
            "1.Đối với các email có định dạng: gmai.com, gmal.com, gmil.com.com, gmail.con, gamil.com, gmall.com, gmaol.com, outlook.con, @hotmail.con, @yahoo.con, @gmaik.",
            "CS chủ động sửa thành định dạng mail đúng và phản hồi cho khách hàng/tài xế, không cần liên hệ xác minh địa chỉ mail. Trường hợp không sửa mail nhưng vẫn gửi mail phản hồi => lỗi ZT",
            "2. Đối với các email có định dạng sai khác",
            "Lấy SĐT/user ID ở mục contact information kiểm tra trên hệ thống Bizops",
            "Có mail đúng định dạng: soạn nội dung và gửi đến địa chỉ mail trên hệ thống Admin",
            "Không có mail đúng định dạng: gửi phản hồi đến email đang có => Resolve case.",
            "Trường hợp KH/TX liên hệ lại khiếu nại không nhận được email, CS check case liên quan nếu thấy đã gửi mail cho KH/TX, báo KH/TX be đã gửi mail vào [địa chỉ mail KH/TX đã đăng kí trên app], nếu KH/TX báo mail đó lỗi, CS cung cấp kết quả theo mail đã gửi và hướng dẫn KH tự thay đổi email trên app",
            "Nếu là TX thì CS thông tin cho TX việc mail trên hệ thống đang không chính xác => thực hiện quy trình đổi mail cho TX",
            "Lưu ý:",
            "Không gửi mail theo quy trình: lỗi ZT",
        ]
    )


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
