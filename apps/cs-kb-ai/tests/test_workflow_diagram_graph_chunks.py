from __future__ import annotations

import unittest

from app.openrouter import workflow_payload_to_units
from app.retrieval import build_display_context, retrieval_display_contract, source_anchor_for_row
from app.text_processing import classify_document
from app.workflow_v3 import compile_workflow_v3_payload, workflow_v3_quality_error_from_report


INBOUND_CALL_FILENAME = "All_Quy trình xử lý cuộc gọi vào-Từ 16.09.2025.pdf"
VISIBLE_STEP_CODES = [
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "8.1",
    "8.2",
    "9",
    "10",
    "10.1",
    "10.2",
    "11",
    "12",
    "13",
    "13.1",
    "13.2",
    "14",
    "15",
    "15.1",
    "15.2",
    "16",
    "17",
    "18",
]


def node(step_code: str, text: str, node_type: str = "action", x: int = 100, y: int = 100, lane: str = "Agent", phase: str = "Body") -> dict:
    return {
        "id": f"n{step_code.replace('.', '_')}",
        "step_code": step_code,
        "text": text,
        "node_type": node_type,
        "shape_kind": "diamond" if node_type == "decision" else "rectangle",
        "lane": lane,
        "phase": phase,
        "bbox": [x, y, x + 180, y + 70],
    }


INBOUND_CALL_CANVAS = {
    "document_metadata": {
        "title": "All_ Quy trình xử lý cuộc gọi vào_Áp dụng từ 16/09/2025",
        "effective_from": "2025-09-16",
        "document_type": "workflow_diagram",
        "actors": ["KH/Partner/NH", "Agent", "L2 ESC/TL BPLQ"],
        "audience": ["customer_service"],
        "risk_level": "high",
    },
    "canvas": {
        "pages": [
            {
                "page": 1,
                "image_size": [3683, 2522],
                "lanes": [
                    {"id": "lane_kh", "title": "KH/Partner/NH", "bbox": [30, 250, 160, 590]},
                    {"id": "lane_agent", "title": "Agent", "bbox": [30, 590, 160, 1950]},
                    {"id": "lane_l2", "title": "L2 ESC/TL BPLQ", "bbox": [30, 1950, 160, 2180]},
                    {"id": "lane_guide", "title": "Hướng dẫn", "bbox": [30, 2180, 160, 2500]},
                ],
                "nodes": [
                    {"id": "start", "text": "Thực hiện cuộc gọi vào", "node_type": "start", "shape_kind": "oval", "lane": "KH/Partner/NH", "phase": "Open", "bbox": [200, 360, 370, 480]},
                    node("1", "1. Chào KH/Partner/NH và xác nhận nhu cầu hỗ trợ (a)", x=230, y=610, phase="Open"),
                    node("2", "2. Xác minh thông tin KH/Partner/NH theo quy định", x=230, y=750, phase="Open"),
                    node("3", "3. CÓ địa chỉ email?", "decision", x=480, y=1025, phase="Open"),
                    node("4", "4. Email KH/Partner/NH cung cấp đúng định dạng?", "decision", x=760, y=1025, phase="Open"),
                    node("5", "5. Xác nhận lại Email với KH/Partner/NH", x=768, y=643, phase="Open"),
                    node("6", "6. KH/Partner/NH đã trình bày vấn đề trước đó?", "decision", x=910, y=1025, phase="Body"),
                    node("7", "7. Nhờ KH/Partner/NH cung cấp Email", x=474, y=593, phase="Open"),
                    node("8", "8. KH/Partner/NH đồng ý cung cấp?", "decision", x=930, y=650, phase="Open"),
                    node("8.1", "8.1. Note email KH/Partner/NH cung cấp vào ô \"Back up email\".", x=1094, y=645, phase="Open"),
                    node("8.2", "8.2 Thông báo KH/Partner/NH trường hợp KH/Partner/NH không cung cấp địa chỉ Email Be chỉ có thể phản hồi cho KH/Partner/NH qua 1 kênh duy nhất là qua SĐT đăng ký. Để hỗ trợ KH/Partner/NH nhờ KH/Partner/NH lưu ý điện thoại", x=1286, y=631, phase="Open"),
                    node("9", "9. Vấn đề thuộc team Agent tiếp nhận phụ trách?", "decision", x=1540, y=620, phase="Body"),
                    node("10", "10. Vấn đề của team Agent tiếp nhận phụ trách?", "decision", x=1760, y=620, phase="Body"),
                    node("10.1", "10.1. Vấn đề của team Agent tiếp nhận phụ trách: Agent xử lý và tạo case tương ứng. Vấn đề của team còn lại, Agent hướng dẫn KH/Partner/NH liên hệ lại đúng kênh theo quy định", x=1688, y=635, phase="Body"),
                    node("10.2", "10.2. Hướng dẫn KH/Partner/NH liên hệ lại đúng kênh hỗ trợ theo quy định", x=2118, y=648, phase="Body"),
                    node("11", "11. Hỗ trợ KH/Partner/NH theo quy trình xử lý vấn đề tương ứng", x=2125, y=1044, phase="Body"),
                    node("12", "12. Cần hỏi ý kiến Agent Layer 2 / Teamlead?", "decision", x=2350, y=1090, lane="L2 ESC/TL BPLQ", phase="Body"),
                    node("13", "13. KH/Partner/NH cần hỗ trợ thêm vấn đề khác?", "decision", x=2462, y=454, phase="Close"),
                    node("13.1", "13.1. Khai thác vấn đề và hỗ trợ theo quy định", x=2633, y=1055, phase="Close"),
                    node("13.2", "13.2. Xác nhận, chào kết và mời đánh giá chất lượng hỗ trợ", x=3215, y=649, phase="Close"),
                    node("14", "14. Lưu trữ thông tin cuộc gọi", x=3219, y=903, phase="Close"),
                    node("15", "15. Không giải quyết được ngay trong call?", "decision", x=2460, y=1310, phase="Body"),
                    node("15.1", "15.1. Hẹn KH/Partner/NH thời gian liên hệ lại sau khi kiểm tra thêm", x=2534, y=1320, phase="Body"),
                    node("15.2", "15.2. Hỏi ý kiến Agent Layer 2 / Teamlead để được hướng dẫn xử lý", x=2681, y=1320, lane="L2 ESC/TL BPLQ", phase="Body"),
                    node("16", "16. Agent Layer 2 / Teamlead hướng dẫn Agent phương án xử lý", x=2780, y=1770, lane="L2 ESC/TL BPLQ", phase="Body"),
                    node("17", "17. Agent phản hồi KH/Partner/NH theo hướng dẫn đã được duyệt", x=2980, y=1770, phase="Body"),
                    node("18", "18. Hoàn tất cuộc gọi và cập nhật kết quả xử lý", x=3180, y=1770, phase="Close"),
                    {"id": "end", "text": "End", "node_type": "end", "shape_kind": "oval", "lane": "KH/Partner/NH", "phase": "Close", "bbox": [3370, 287, 3530, 377]},
                ],
                "edges": [
                    {"from_node": "start", "to_step_code": "1", "condition": "next", "confidence": 0.95},
                    {"from_step_code": "1", "to_step_code": "2", "condition": "next", "confidence": 0.95},
                    {"from_step_code": "2", "to_step_code": "3", "condition": "next", "confidence": 0.95},
                    {"from_step_code": "3", "to_step_code": "4", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "3", "to_step_code": "7", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "4", "to_step_code": "5", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "4", "to_step_code": "7", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "5", "to_step_code": "6", "condition": "next", "confidence": 0.92},
                    {"from_step_code": "6", "to_step_code": "9", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "6", "to_step_code": "7", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "7", "to_step_code": "8", "condition": "next", "confidence": 0.92},
                    {"from_step_code": "8", "to_step_code": "8.1", "condition": "yes", "confidence": 0.93},
                    {"from_step_code": "8", "to_step_code": "8.2", "condition": "no", "confidence": 0.93},
                    {"from_step_code": "8.1", "to_step_code": "9", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "8.2", "to_step_code": "9", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "9", "to_step_code": "10", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "9", "to_step_code": "12", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "10", "to_step_code": "10.1", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "10", "to_step_code": "10.2", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "10.1", "to_step_code": "11", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "10.2", "to_step_code": "13", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "11", "to_step_code": "12", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "12", "to_step_code": "15", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "12", "to_step_code": "13", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "13", "to_step_code": "13.1", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "13", "to_step_code": "13.2", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "13.1", "to_step_code": "11", "condition": "next", "confidence": 0.88},
                    {"from_step_code": "13.2", "to_step_code": "14", "condition": "next", "confidence": 0.92},
                    {"from_step_code": "14", "to_node": "end", "condition": "next", "confidence": 0.92},
                    {"from_step_code": "15", "to_step_code": "15.2", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "15", "to_step_code": "15.1", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "15.1", "to_step_code": "16", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "15.2", "to_step_code": "16", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "16", "to_step_code": "17", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "17", "to_step_code": "18", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "18", "to_node": "end", "condition": "next", "confidence": 0.9},
                ],
                "annotations": [
                    {"id": "ann_a", "text": "(a) Agent sử dụng lời chào theo kịch bản mở đầu cuộc gọi.", "annotation_type": "annotation", "attached_to_step_codes": ["1"], "bbox": [270, 699, 296, 723]},
                    {"id": "ann_b", "text": "(b) Trường hợp cần xác minh email, thực hiện theo Quy định xác minh địa chỉ email.docx", "annotation_type": "annotation", "attached_to_step_codes": ["8", "8.1"], "bbox": [1080, 850, 1500, 900]},
                    {"id": "ann_c", "text": "(c) Nếu không cần hỗ trợ thêm, chào kết và mời đánh giá chất lượng cuộc gọi.", "annotation_type": "macro_script", "attached_to_step_codes": ["13", "13.2"], "bbox": [3161, 2171, 3641, 2494]},
                ],
                "relations": [
                    {"target_title": "Quy định xác minh địa chỉ email.docx", "relation_type": "references", "evidence_text": "(b) Trường hợp cần xác minh email, thực hiện theo Quy định xác minh địa chỉ email.docx", "attached_to_step_codes": ["8", "8.1"], "bbox": [1080, 850, 1500, 900]},
                ],
            }
        ]
    },
}

RAW_INBOUND_CALL_TEXT = "\n".join(
    [
        "All_ Quy trình xử lý cuộc gọi vào_Áp dụng từ 16/09/2025",
        *(f"{code}. visible workflow step" for code in VISIBLE_STEP_CODES),
        "(a) Agent sử dụng lời chào theo kịch bản mở đầu cuộc gọi.",
        "(b) Trường hợp cần xác minh email, thực hiện theo Quy định xác minh địa chỉ email.docx",
        "(c) Nếu không cần hỗ trợ thêm, chào kết và mời đánh giá chất lượng cuộc gọi.",
    ]
)


def compile_inbound_call_payload():
    payload, report, _canvas = compile_workflow_v3_payload(
        filename=INBOUND_CALL_FILENAME,
        raw_text=RAW_INBOUND_CALL_TEXT,
        transcription=INBOUND_CALL_CANVAS,
        visual_context={},
    )
    assert payload is not None
    assert workflow_v3_quality_error_from_report(report) == ""
    return payload, report


def units_by_type(units: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for unit in units:
        grouped.setdefault(str(unit.get("unit_type") or ""), []).append(unit)
    return grouped


class InboundCallWorkflowDiagramTest(unittest.TestCase):
    def test_inbound_call_pdf_filename_routes_to_workflow_diagram(self) -> None:
        classification = classify_document(INBOUND_CALL_FILENAME, "application/pdf", "")

        self.assertEqual(classification.document_type, "workflow_diagram")
        self.assertEqual(classification.source_type, "diagram_pdf")

    def test_graph_preserves_visible_steps_and_branches(self) -> None:
        payload, report = compile_inbound_call_payload()
        graph = payload.workflow_graph.model_dump()

        self.assertEqual(report["visible_step_codes"], VISIBLE_STEP_CODES)
        self.assertEqual(report["missing_step_codes"], [])
        decision_codes = {node["step_code"] for node in graph["nodes"] if node["type"] == "decision"}
        self.assertTrue({"3", "4", "6", "8", "9", "10", "12", "13", "15"}.issubset(decision_codes))
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("node_8", "yes", "node_8_1"), edge_keys)
        self.assertIn(("node_8", "no", "node_8_2"), edge_keys)
        self.assertIn(("node_16", "next", "node_17"), edge_keys)

    def test_graph_first_units_include_source_text_branches_paths_and_visual_refs(self) -> None:
        payload, _report = compile_inbound_call_payload()
        units = workflow_payload_to_units(payload, INBOUND_CALL_FILENAME)
        grouped = units_by_type(units)

        self.assertIn("full_workflow_diagram", grouped)
        self.assertEqual(len(grouped.get("workflow_phase", [])), 3)
        self.assertIn("workflow_step", grouped)
        self.assertIn("decision_node", grouped)
        self.assertIn("decision_branch", grouped)
        self.assertIn("workflow_path", grouped)
        self.assertIn("script_block", grouped)
        self.assertIn("annotation", grouped)
        self.assertIn("relation_to_sop", grouped)

        step_units = {unit["metadata"].get("step_code"): unit for unit in grouped["workflow_step"]}
        self.assertTrue(set(VISIBLE_STEP_CODES) - {"3", "4", "6", "8", "9", "10", "12", "13", "15"} <= set(step_units))
        step_8_2 = step_units["8.2"]
        self.assertTrue(step_8_2["metadata"]["source_text"].startswith("8.2 Thông báo KH/Partner/NH trường hợp"))
        self.assertIn("Be chỉ có thể phản hồi", step_8_2["metadata"]["source_text"])
        self.assertIn("Be chỉ có thể phản hồi", step_8_2["content"])
        self.assertNotEqual(step_8_2["metadata"]["display_text"], step_8_2["metadata"]["retrieval_text"])
        self.assertTrue(all(ref.get("page") == 1 and len(ref.get("bbox", [])) == 4 for ref in step_8_2["source_refs"]))

        branches = grouped["decision_branch"]
        branch_8_yes = next(unit for unit in branches if unit["metadata"].get("from_step_code") == "8" and unit["metadata"].get("condition") == "yes")
        branch_8_no = next(unit for unit in branches if unit["metadata"].get("from_step_code") == "8" and unit["metadata"].get("condition") == "no")
        self.assertIn("Decision 8", branch_8_yes["content"])
        self.assertIn("8.1", branch_8_yes["content"])
        self.assertIn("Decision 8", branch_8_no["content"])
        self.assertIn("8.2", branch_8_no["content"])
        self.assertIn("không cung cấp địa chỉ Email", branch_8_no["content"])

        self.assertTrue(any("15.2" in unit["content"] and "16" in unit["content"] and "17" in unit["content"] and "18" in unit["content"] for unit in grouped["workflow_path"]))
        self.assertTrue(any(unit["metadata"].get("attached_to_step_codes") == ["1"] for unit in grouped["annotation"]))
        self.assertTrue(any("Quy định xác minh địa chỉ email.docx" in unit["metadata"].get("target_title", "") for unit in grouped["relation_to_sop"]))
        self.assertTrue(all(ref.get("page") == 1 and len(ref.get("bbox", [])) == 4 for unit in grouped["workflow_step"] for ref in unit["source_refs"]))

    def test_workflow_result_contract_opens_visual_diagram_with_bbox_highlight(self) -> None:
        payload, _report = compile_inbound_call_payload()
        units = workflow_payload_to_units(payload, INBOUND_CALL_FILENAME)
        grouped = units_by_type(units)
        branch = next(unit for unit in grouped["decision_branch"] if unit["metadata"].get("from_step_code") == "8" and unit["metadata"].get("condition") == "no")
        row = {
            "document_id": "doc-1",
            "version_id": "version-1",
            "chunk_id": "chunk-branch-8-no",
            "title": payload.workflow_graph.title,
            "section": branch["unit_type"],
            "heading": branch["title"],
            "content": branch["content"],
            "metadata": branch["metadata"],
            "version_number": 1,
        }

        display_context = build_display_context(row, None)
        source_anchor = source_anchor_for_row(row, branch["metadata"])
        contract = retrieval_display_contract(row, branch["metadata"], display_context, source_anchor)

        self.assertEqual(display_context.display_unit_type, "workflow_diagram")
        self.assertFalse(display_context.highlight_failed)
        self.assertEqual(display_context.highlights[0].match_strategy, "visual_bbox")
        self.assertEqual(contract.open_mode, "workflow_diagram")
        self.assertTrue(contract.highlight_source_refs[0]["bbox"])


if __name__ == "__main__":
    unittest.main()
