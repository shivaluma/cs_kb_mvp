from __future__ import annotations

import copy
import unittest

from app.workflow_v3 import compile_workflow_v3_payload, workflow_v3_quality_error_from_report


EMAIL_WORKFLOW_CANVAS = {
    "document_metadata": {
        "title": "All_Mail (ho.tro@be.com.vn)_Quy trình xác minh tài khoản",
        "effective_from": "2024-12-03",
        "actors": ["KH/TX", "CS"],
        "audience": ["customer", "driver"],
        "risk_level": "high",
    },
    "canvas": {
        "pages": [
            {
                "page": 1,
                "image_size": [2483, 1732],
                "lanes": [
                    {"id": "lane_kh_tx", "title": "KH/TX", "bbox": [40, 99, 110, 348]},
                    {"id": "lane_cs", "title": "CS", "bbox": [40, 348, 110, 1702]},
                ],
                "nodes": [
                    {"id": "start", "text": "KH/TX liên hệ qua email hotro@be.com.vn", "node_type": "start", "shape_kind": "oval", "lane": "KH/TX", "bbox": [387, 152, 619, 265]},
                    {"id": "d1", "step_code": "1", "text": "1. KH/TX hỏi các thông tin chung? (*)", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [403, 392, 602, 568]},
                    {"id": "a11", "step_code": "1.1", "text": "1.1. CS cung cấp thông tin theo quy định cho KH/TX", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [781, 424, 1005, 536], "terminal_state": "resolved"},
                    {"id": "a12", "step_code": "1.2", "text": "1.2. CS dùng email KH/TX gửi lên (email A) kiểm tra trên hệ thống có tài khoản đăng ký với email tương ứng?", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [360, 629, 742, 772]},
                    {"id": "d2", "step_code": "2", "text": "2. Có tài khoản tương ứng với email KH/TX gửi?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [750, 626, 938, 782]},
                    {"id": "d3", "step_code": "3", "text": "3. Vấn đề cần hỗ trợ phát sinh trên đúng tài khoản của KH/TX?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [752, 906, 948, 1074]},
                    {"id": "d4", "step_code": "4", "text": "4. Đủ thông tin để xử lý?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [761, 1147, 939, 1318]},
                    {"id": "a5", "step_code": "5", "text": "5. Xử lý theo quy trình/quy định tương ứng", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [732, 1471, 968, 1568], "terminal_state": "continue_to_related_process"},
                    {"id": "d6", "step_code": "6", "text": "6. Case thái độ tài xế/case có vấn đề SI?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [421, 1144, 690, 1380]},
                    {"id": "a61", "step_code": "6.1", "text": "6.1. Lấy SĐT KH/TX tương ứng để liên hệ khai thác thêm thông tin. liên hệ không thành công gửi mail", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [166, 1135, 361, 1324]},
                    {"id": "a62", "step_code": "6.2", "text": "6.2. Phản hồi email nhờ KH/TX cung cấp thêm thông tin (status Resolved) (**)", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [445, 1461, 668, 1577], "terminal_state": "resolved"},
                    {"id": "a92", "step_code": "9.2", "text": "9.2. CS gọi ra cho KH/TX theo thông tin tài khoản của Trip ID/Order ID/SĐT đăng ký Be mà KH/TX cung cấp để xác minh thông tin", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1069, 849, 1476, 1033]},
                    {"id": "d10", "step_code": "10", "text": "10. Liên hệ thành công?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [1277, 1118, 1385, 1226]},
                    {"id": "a101", "step_code": "10.1", "text": "10.1. Xác minh có phải KH/TX đang cần hỗ trợ về vấn đề.... và dùng mail A để liên hệ Be không", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1520, 1117, 1770, 1232]},
                    {"id": "a102", "step_code": "10.2", "text": "10.2. Gửi mail cho A thông báo Be đã liên hệ với SĐT đăng ký Be của tài khoản phát sinh trip/vấn đề để xác minh thông tin nhưng không thành công, vui lòng liên hệ vào hotline 1900232345 (đối với KH) hoặc Call in app (đối với TX) bằng SĐT đăng ký Be của tài khoản phát sinh trip/vấn đề để được hỗ trợ thêm", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1129, 1354, 1533, 1576], "terminal_state": "closed_with_response"},
                    {"id": "d11", "step_code": "11", "text": "11. KH/TX xác nhận đúng?", "node_type": "decision", "shape_kind": "diamond", "lane": "KH/TX", "bbox": [1725, 240, 1852, 331]},
                    {"id": "a111", "step_code": "11.1", "text": "11.1. Tiếp tục hỗ trợ theo quy trình và phản hồi theo email A", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1674, 687, 1902, 770], "terminal_state": "continue_to_related_process"},
                    {"id": "a112", "step_code": "11.2", "text": "11.2. CS phản hồi mail A là chưa thể hỗ trợ vì thông tin A không trùng khớp với thông tin Trip/vấn đề cần hỗ trợ", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1894, 428, 2233, 558], "terminal_state": "closed_with_response"},
                    {"id": "d12", "step_code": "12", "text": "12 Cung cấp trip ID/order ID/số điện thoại đăng ký Be?", "node_type": "decision", "shape_kind": "diamond", "lane": "CS", "bbox": [1089, 604, 1423, 824]},
                    {"id": "a13", "step_code": "13", "text": "13. CS phản hồi email xin thông tin số điện thoại đăng ký Be và thông tin liên quan đến vấn đề cần hỗ trợ để CS có thể xử lý case (status resolved)", "node_type": "action", "shape_kind": "rectangle", "lane": "CS", "bbox": [1174, 405, 1475, 556], "terminal_state": "resolved"},
                    {"id": "end", "text": "End", "node_type": "end", "shape_kind": "oval", "lane": "KH/TX", "bbox": [2162, 155, 2307, 248]},
                ],
                "edges": [
                    {"from_node": "start", "to_step_code": "1", "condition": "next", "confidence": 0.92},
                    {"from_step_code": "1", "to_step_code": "1.1", "condition": "yes", "confidence": 0.94},
                    {"from_step_code": "1", "to_step_code": "1.2", "condition": "no", "confidence": 0.94},
                    {"from_step_code": "1.2", "to_step_code": "2", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "2", "to_step_code": "3", "condition": "yes", "confidence": 0.93},
                    {"from_step_code": "2", "to_step_code": "12", "condition": "no", "confidence": 0.93},
                    {"from_step_code": "3", "to_step_code": "4", "condition": "yes", "confidence": 0.93},
                    {"from_step_code": "3", "to_step_code": "9.2", "condition": "no", "confidence": 0.93},
                    {"from_step_code": "4", "to_step_code": "5", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "4", "to_step_code": "6", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "6", "to_step_code": "6.1", "condition": "yes", "confidence": 0.91},
                    {"from_step_code": "6", "to_step_code": "6.2", "condition": "no", "confidence": 0.91},
                    {"from_step_code": "12", "to_step_code": "13", "condition": "no", "confidence": 0.92},
                    {"from_step_code": "12", "to_step_code": "9.2", "condition": "yes", "confidence": 0.92},
                    {"from_step_code": "9.2", "to_step_code": "10", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "10", "to_step_code": "10.1", "condition": "yes", "confidence": 0.9},
                    {"from_step_code": "10", "to_step_code": "10.2", "condition": "no", "confidence": 0.9},
                    {"from_step_code": "10.1", "to_step_code": "11", "condition": "next", "confidence": 0.9},
                    {"from_step_code": "11", "to_step_code": "11.1", "condition": "yes", "confidence": 0.9},
                    {"from_step_code": "11", "to_step_code": "11.2", "condition": "no", "confidence": 0.9},
                    {"from_step_code": "1.1", "to_node": "end", "condition": "next", "confidence": 0.82},
                ],
                "annotations": [
                    {"id": "note_info", "text": "(*) Thông tin chung là các thông tin được công bố trên website và các phương tiện truyền thông khác, CS không cần kiểm tra thêm tại các hệ thống làm việc", "annotation_type": "annotation", "attached_to_step_codes": ["1"], "bbox": [130, 381, 370, 579]},
                    {"id": "note_si", "text": "(**) Riêng case SI nếu liên hệ không thành công, CS gửi mail cho KH/TX, resolve case và tạo case Internal chuyển SI theo quy định", "annotation_type": "annotation", "attached_to_step_codes": ["6", "6.2"], "bbox": [416, 906, 670, 1076]},
                    {"id": "note_ref", "text": "(*) Lưu ý chung: Quy định xác minh tài khoản TX, KH.xlsx", "annotation_type": "annotation", "attached_to_step_codes": [], "bbox": [737, 110, 1312, 169]},
                ],
                "relations": [
                    {"target_title": "Quy định xác minh tài khoản TX, KH.xlsx", "relation_type": "requires", "evidence_text": "(*) Lưu ý chung: Quy định xác minh tài khoản TX, KH.xlsx", "bbox": [737, 110, 1312, 169]},
                ],
            }
        ]
    },
}


RAW_TEXT = """
1. KH/TX hỏi các thông tin chung?
1.1. CS cung cấp thông tin theo quy định cho KH/TX
1.2. CS dùng email KH/TX gửi lên (email A) kiểm tra trên hệ thống có tài khoản đăng ký với email tương ứng?
2. Có tài khoản tương ứng với email KH/TX gửi?
3. Vấn đề cần hỗ trợ phát sinh trên đúng tài khoản của KH/TX?
4. Đủ thông tin để xử lý?
5. Xử lý theo quy trình/quy định tương ứng
6. Case thái độ tài xế/case có vấn đề SI?
6.1. Lấy SĐT KH/TX tương ứng để liên hệ khai thác thêm thông tin
6.2. Phản hồi email nhờ KH/TX cung cấp thêm thông tin
9.2. CS gọi ra cho KH/TX theo thông tin tài khoản của Trip ID/Order ID/SĐT đăng ký Be
10. Liên hệ thành công?
10.1. Xác minh có phải KH/TX đang cần hỗ trợ về vấn đề
10.2. Gửi mail cho A thông báo Be đã liên hệ không thành công
11. KH/TX xác nhận đúng?
11.1. Tiếp tục hỗ trợ theo quy trình và phản hồi theo email A
11.2. CS phản hồi mail A là chưa thể hỗ trợ
12 Cung cấp trip ID/order ID/số điện thoại đăng ký Be?
13. CS phản hồi email xin thông tin số điện thoại đăng ký Be
"""


class WorkflowV3CompilerTest(unittest.TestCase):
    def test_email_workflow_preserves_decisions_edges_annotations_and_relation(self) -> None:
        payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=EMAIL_WORKFLOW_CANVAS,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(workflow_v3_quality_error_from_report(report), "")
        graph = payload.workflow_graph.model_dump()
        decision_codes = {node["step_code"] for node in graph["nodes"] if node["type"] == "decision"}
        self.assertTrue({"1", "2", "3", "4", "6", "10", "11", "12"}.issubset(decision_codes))
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("start", "next", "node_1"), edge_keys)
        self.assertIn(("node_3", "no", "node_9_2"), edge_keys)
        self.assertIn(("node_4", "no", "node_6"), edge_keys)
        self.assertIn(("node_6", "yes", "node_6_1"), edge_keys)
        self.assertIn(("node_6", "no", "node_6_2"), edge_keys)
        self.assertIn(("node_12", "yes", "node_9_2"), edge_keys)
        self.assertIn(("node_12", "no", "node_13"), edge_keys)
        self.assertIn(("node_10", "yes", "node_10_1"), edge_keys)
        self.assertIn(("node_10", "no", "node_10_2"), edge_keys)
        self.assertIn(("node_11", "yes", "node_11_1"), edge_keys)
        self.assertIn(("node_11", "no", "node_11_2"), edge_keys)
        self.assertNotIn(("node_3", "no", "node_12"), edge_keys)
        node_types = {node["id"]: node["type"] for node in graph["nodes"]}
        self.assertEqual(node_types["start"], "start")
        self.assertEqual(node_types["end"], "end")
        for step_code in {"1.1", "5", "6.1", "6.2", "13", "10.2", "11.1", "11.2"}:
            node_id = f"node_{step_code.replace('.', '_')}"
            self.assertIn((node_id, "next", "end"), edge_keys)
        annotation_text = "\n".join(annotation.content for annotation in payload.annotations)
        self.assertIn("Riêng case SI", annotation_text)
        annotations = [annotation.model_dump() for annotation in payload.annotations]
        info_note = next(annotation for annotation in annotations if "Thông tin chung" in annotation["content"])
        si_note = next(annotation for annotation in annotations if "Riêng case SI" in annotation["content"])
        self.assertEqual(info_note["attached_to"], "node_1")
        self.assertEqual(si_note["attached_to"], "node_6_1")
        relation_units = [unit for unit in payload.atomic_units if unit.unit_type == "related_document"]
        self.assertEqual(relation_units[0].metadata["relation_type"], "requires")
        self.assertEqual(relation_units[0].metadata["target_title"], "Quy định xác minh tài khoản TX, KH.xlsx")
        self.assertNotIn("not decision", str(graph).lower())
        self.assertGreaterEqual(graph["graph_fidelity_score"], 0.9)
        self.assertTrue(graph["repair_applied"])
        self.assertEqual(graph["missing_terminal_edges"], [])
        self.assertEqual(graph["decision_edges_review_required"], 16)
        self.assertEqual(graph["unresolved_relations"][0]["target_title"], "Quy định xác minh tài khoản TX, KH.xlsx")

    def test_missing_start_end_and_terminal_edges_are_synthesized(self) -> None:
        transcription = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        page = transcription["canvas"]["pages"][0]
        page["nodes"] = [node for node in page["nodes"] if node.get("node_type") not in {"start", "end"}]
        page["edges"] = [
            edge for edge in page["edges"]
            if edge.get("from_node") != "start" and edge.get("to_node") != "end"
        ]

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=transcription,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        graph = payload.workflow_graph.model_dump()
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes_by_id["start"]["title"], "KH/TX liên hệ qua email hotro@be.com.vn")
        self.assertEqual(nodes_by_id["start"]["type"], "start")
        self.assertEqual(nodes_by_id["start"]["lane_id"], "lane_customer_driver")
        self.assertEqual(nodes_by_id["end"]["type"], "end")
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("start", "next", "node_1"), edge_keys)
        self.assertIn(("node_13", "next", "end"), edge_keys)
        self.assertIn("workflow_v3_start_node_synthesized", report["warnings"])
        self.assertIn("workflow_v3_end_node_synthesized", report["warnings"])

    def test_multi_step_visual_node_is_split_so_branch_targets_resolve(self) -> None:
        raw_text = """
7. Nhờ KH/Partner/NH cung cấp Email
8. KH/Partner/NH đồng ý cung cấp?
8.1. Note email KH/Partner/NH cung cấp vào ô Back up email
8.2. Thông báo KH/Partner/NH trường hợp không cung cấp địa chỉ Email
9. Vấn đề KH/Partner/NH yêu cầu hỗ trợ chỉ thuộc team Agent phụ trách?
16. Agent tiếp nhận lại thông tin
17. Kiểm tra và cung cấp hướng xử lý / kết quả cho Agent
18. Phản hồi TX/KH dựa trên hướng dẫn / kết quả được cung cấp
"""
        transcription = {
            "document_metadata": {"title": "Inbound call workflow"},
            "canvas": {
                "pages": [
                    {
                        "page": 1,
                        "image_size": [3600, 1600],
                        "nodes": [
                            {"id": "start", "text": "Thực hiện cuộc gọi vào", "node_type": "start", "shape_kind": "oval", "bbox": [100, 100, 260, 180]},
                            {
                                "id": "step_7_group",
                                "text": "7. Nhờ\nKH/Partner/NH\ncung cấp Email\n8.1. Note email\nKH/Partner/NH cung cấp vào ô Back up email",
                                "node_type": "action",
                                "shape_kind": "rectangle",
                                "lane": "Agent",
                                "bbox": [350, 340, 650, 520],
                            },
                            {
                                "id": "step_8",
                                "step_code": "8",
                                "text": "8. KH/Partner/NH đồng ý cung cấp?",
                                "node_type": "decision",
                                "shape_kind": "diamond",
                                "lane": "Agent",
                                "bbox": [700, 350, 900, 540],
                            },
                            {
                                "id": "step_8_2",
                                "step_code": "8.2",
                                "text": "8.2. Thông báo KH/Partner/NH trường hợp KH/Partner/NH không cung cấp địa chỉ Email Be chỉ có thể phản hồi qua SĐT đăng ký",
                                "node_type": "action",
                                "shape_kind": "rectangle",
                                "lane": "Agent",
                                "bbox": [700, 620, 980, 760],
                            },
                            {"id": "step_9", "step_code": "9", "text": "9. Vấn đề KH/Partner/NH yêu cầu hỗ trợ chỉ thuộc team Agent phụ trách?", "node_type": "decision", "shape_kind": "diamond", "lane": "Agent", "bbox": [1060, 360, 1280, 540]},
                            {"id": "step_10_1", "step_code": "10.1", "text": "10.1. Agent xử lý và tạo case tương ứng", "node_type": "action", "shape_kind": "rectangle", "lane": "Agent", "bbox": [1360, 330, 1580, 450], "terminal_state": "resolved"},
                            {"id": "step_10_2", "step_code": "10.2", "text": "10.2. Hướng dẫn KH/Partner/NH liên hệ lại đúng kênh hỗ trợ theo quy định", "node_type": "action", "shape_kind": "rectangle", "lane": "Agent", "bbox": [1360, 500, 1580, 620], "terminal_state": "closed_with_response"},
                            {"id": "step_16", "step_code": "16", "text": "16. Agent tiếp nhận lại thông tin", "node_type": "action", "shape_kind": "rectangle", "lane": "Agent", "bbox": [1880, 700, 2100, 820]},
                            {"id": "step_17", "step_code": "17", "text": "17. Kiểm tra và cung cấp hướng xử lý / kết quả cho Agent", "node_type": "action", "shape_kind": "rectangle", "lane": "L2 ESC/TL BPLQ", "bbox": [2180, 700, 2420, 820]},
                            {"id": "step_18", "step_code": "18", "text": "18. Phản hồi TX/KH dựa trên hướng dẫn / kết quả được cung cấp", "node_type": "action", "shape_kind": "rectangle", "lane": "Agent", "bbox": [2500, 700, 2780, 820], "terminal_state": "resolved"},
                            {"id": "end", "text": "End", "node_type": "end", "shape_kind": "oval", "bbox": [3000, 100, 3120, 180]},
                        ],
                        "edges": [
                            {"from_node": "start", "to_step_code": "7", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "7", "to_step_code": "8", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "8", "to_step_code": "8.1", "condition": "yes", "confidence": 0.9},
                            {"from_step_code": "8", "to_step_code": "8.2", "condition": "no", "confidence": 0.9},
                            {"from_step_code": "8.1", "to_step_code": "9", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "8.2", "to_step_code": "9", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "9", "to_step_code": "10.1", "condition": "yes", "confidence": 0.9},
                            {"from_step_code": "9", "to_step_code": "10.2", "condition": "no", "confidence": 0.9},
                            {"from_step_code": "16", "to_step_code": "17", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "17", "to_step_code": "18", "condition": "next", "confidence": 0.9},
                        ],
                    }
                ]
            },
        }

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="inbound_call.pdf",
            raw_text=raw_text,
            transcription=transcription,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        graph = payload.workflow_graph.model_dump()
        nodes_by_code = {node["step_code"]: node for node in graph["nodes"] if node.get("step_code")}
        self.assertIn("8.1", nodes_by_code)
        self.assertIn("Note email", nodes_by_code["8.1"]["content"])
        self.assertNotIn("8.1", report["missing_step_codes"])
        self.assertFalse(any("edge_endpoint_not_resolved:8->8.1" == warning for warning in report["warnings"]))
        self.assertFalse(any("workflow_v3_decision_missing_two_branches:8" == blocker for blocker in report["blockers"]))
        self.assertFalse(any("workflow_v3_action_missing_terminal_or_outgoing:16" == blocker for blocker in report["blockers"]))
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("node_8", "yes", "node_8_1"), edge_keys)
        self.assertIn(("node_8", "no", "node_8_2"), edge_keys)
        self.assertIn(("node_16", "next", "node_17"), edge_keys)

    def test_same_line_decision_group_splits_child_actions_without_inheriting_diamond_type(self) -> None:
        raw_text = (
            "8. KH/Partner/NH đồng ý cung cấp? "
            "8.1. Note email KH/Partner/NH cung cấp vào ô Back up email "
            "8.2. Thông báo KH/Partner/NH trường hợp không cung cấp địa chỉ Email"
        )
        transcription = {
            "document_metadata": {"title": "Inbound call workflow"},
            "canvas": {
                "pages": [
                    {
                        "page": 1,
                        "nodes": [
                            {
                                "id": "decision_8_group",
                                "text": raw_text,
                                "node_type": "decision",
                                "shape_kind": "diamond",
                                "lane": "Agent",
                                "bbox": [700, 350, 980, 760],
                            },
                            {"id": "end", "text": "End", "node_type": "end", "shape_kind": "oval", "bbox": [1100, 350, 1220, 450]},
                        ],
                        "edges": [
                            {"from_step_code": "8", "to_step_code": "8.1", "condition": "yes", "confidence": 0.9},
                            {"from_step_code": "8", "to_step_code": "8.2", "condition": "no", "confidence": 0.9},
                            {"from_step_code": "8.1", "to_node": "end", "condition": "next", "confidence": 0.9},
                            {"from_step_code": "8.2", "to_node": "end", "condition": "next", "confidence": 0.9},
                        ],
                    }
                ]
            },
        }

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="inbound_call.pdf",
            raw_text=raw_text,
            transcription=transcription,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        graph = payload.workflow_graph.model_dump()
        nodes_by_code = {node["step_code"]: node for node in graph["nodes"] if node.get("step_code")}
        self.assertIn("8.1", nodes_by_code)
        self.assertIn("8.2", nodes_by_code)
        self.assertEqual(nodes_by_code["8"]["type"], "decision")
        self.assertEqual(nodes_by_code["8.1"]["type"], "action")
        self.assertEqual(nodes_by_code["8.2"]["type"], "action")
        self.assertNotIn("8.1", report["missing_step_codes"])
        self.assertNotIn("8.2", report["missing_step_codes"])
        self.assertFalse(any("workflow_v3_decision_missing_two_branches:8" == blocker for blocker in report["blockers"]))
        self.assertFalse(any("workflow_v3_branching_node_not_decision" in blocker for blocker in report["blockers"]))
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("node_8", "yes", "node_8_1"), edge_keys)
        self.assertIn(("node_8", "no", "node_8_2"), edge_keys)

    def test_multi_step_split_does_not_treat_quantities_as_step_codes(self) -> None:
        raw_text = "8.2. Thông báo KH/Partner/NH Be chỉ có thể phản hồi qua 1 kênh duy nhất là qua SĐT đăng ký"
        transcription = {
            "document_metadata": {"title": "Inbound call workflow"},
            "canvas": {
                "pages": [
                    {
                        "page": 1,
                        "nodes": [
                            {
                                "id": "step_8_2",
                                "step_code": "8.2",
                                "text": raw_text,
                                "node_type": "action",
                                "shape_kind": "rectangle",
                                "lane": "Agent",
                                "bbox": [700, 620, 980, 760],
                                "terminal_state": "closed_with_response",
                            },
                            {"id": "end", "text": "End", "node_type": "end", "shape_kind": "oval", "bbox": [1100, 350, 1220, 450]},
                        ],
                        "edges": [
                            {"from_step_code": "8.2", "to_node": "end", "condition": "next", "confidence": 0.9},
                        ],
                    }
                ]
            },
        }

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="inbound_call.pdf",
            raw_text=raw_text,
            transcription=transcription,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        graph = payload.workflow_graph.model_dump()
        nodes_by_code = {node["step_code"]: node for node in graph["nodes"] if node.get("step_code")}
        self.assertIn("8.2", nodes_by_code)
        self.assertNotIn("1", nodes_by_code)
        self.assertIn("1 kênh", nodes_by_code["8.2"]["content"])
        self.assertNotIn("1", report["covered_step_codes"])

    def test_boundary_nodes_with_ambiguous_zero_ids_do_not_collide(self) -> None:
        transcription = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        page = transcription["canvas"]["pages"][0]
        for node in page["nodes"]:
            if node.get("node_type") in {"start", "end"}:
                node["id"] = "0"
        page["edges"] = [
            {"from_node": "0", "to_step_code": "1", "condition": "next", "confidence": 0.92},
            {"from_step_code": "1", "to_step_code": "1.1", "condition": "yes", "confidence": 0.94},
            {"from_step_code": "1", "to_step_code": "1.2", "condition": "no", "confidence": 0.94},
            {"from_step_code": "1.2", "to_step_code": "2", "condition": "next", "confidence": 0.9},
            {"from_step_code": "2", "to_step_code": "3", "condition": "yes", "confidence": 0.93},
            {"from_step_code": "2", "to_step_code": "12", "condition": "no", "confidence": 0.93},
            {"from_step_code": "3", "to_step_code": "4", "condition": "yes", "confidence": 0.93},
            {"from_step_code": "3", "to_step_code": "9.2", "condition": "no", "confidence": 0.93},
            {"from_step_code": "4", "to_step_code": "5", "condition": "yes", "confidence": 0.92},
            {"from_step_code": "4", "to_step_code": "6", "condition": "no", "confidence": 0.92},
            {"from_step_code": "6", "to_step_code": "6.1", "condition": "yes", "confidence": 0.91},
            {"from_step_code": "6", "to_step_code": "6.2", "condition": "no", "confidence": 0.91},
            {"from_step_code": "12", "to_step_code": "13", "condition": "no", "confidence": 0.92},
            {"from_step_code": "12", "to_step_code": "9.2", "condition": "yes", "confidence": 0.92},
            {"from_step_code": "9.2", "to_step_code": "10", "condition": "next", "confidence": 0.9},
            {"from_step_code": "10", "to_step_code": "10.1", "condition": "yes", "confidence": 0.9},
            {"from_step_code": "10", "to_step_code": "10.2", "condition": "no", "confidence": 0.9},
            {"from_step_code": "10.1", "to_step_code": "11", "condition": "next", "confidence": 0.9},
            {"from_step_code": "11", "to_step_code": "11.1", "condition": "yes", "confidence": 0.9},
            {"from_step_code": "11", "to_step_code": "11.2", "condition": "no", "confidence": 0.9},
            {"from_step_code": "1.1", "to_node": "0", "condition": "next", "confidence": 0.82},
        ]

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=transcription,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(workflow_v3_quality_error_from_report(report), "")
        graph = payload.workflow_graph.model_dump()
        node_ids = [node["id"] for node in graph["nodes"]]
        self.assertIn("start", node_ids)
        self.assertIn("end", node_ids)
        self.assertEqual(len(node_ids), len(set(node_ids)))
        edge_keys = {(edge["from_node"], edge["condition"], edge["to_node"]) for edge in graph["edges"]}
        self.assertIn(("start", "next", "node_1"), edge_keys)
        self.assertIn(("node_1_1", "next", "end"), edge_keys)
        self.assertFalse(any("workflow_v3_start_has_incoming" in blocker for blocker in report["blockers"]))
        self.assertFalse(any("workflow_v3_end_has_outgoing" in blocker for blocker in report["blockers"]))

    def test_missing_visible_step_blocks_v3_success(self) -> None:
        broken = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        broken["canvas"]["pages"][0]["nodes"] = [
            node for node in EMAIL_WORKFLOW_CANVAS["canvas"]["pages"][0]["nodes"]
            if node.get("step_code") != "6"
        ]

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=broken,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        self.assertIn("6", report["missing_step_codes"])
        self.assertIn("workflow_v3_missing_visible_steps:6", workflow_v3_quality_error_from_report(report))

    def test_branching_node_not_decision_blocks_v3_success(self) -> None:
        broken = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        nodes = [dict(node) for node in EMAIL_WORKFLOW_CANVAS["canvas"]["pages"][0]["nodes"]]
        for node in nodes:
            if node.get("step_code") == "6":
                node["node_type"] = "action"
                node["shape_kind"] = "rectangle"
        broken["canvas"]["pages"][0]["nodes"] = nodes

        _payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=broken,
            visual_context={},
        )

        self.assertTrue(any("workflow_v3_branching_node_not_decision:6" == blocker for blocker in report["blockers"]))

    def test_decision_marked_not_decision_metadata_is_repaired_out_of_graph(self) -> None:
        broken = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        for node in broken["canvas"]["pages"][0]["nodes"]:
            if node.get("step_code") == "4":
                node["metadata"] = {"review_status": "not decision"}

        payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=broken,
            visual_context={},
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        graph = payload.workflow_graph.model_dump()
        self.assertNotIn("not decision", str(graph).lower())
        self.assertIn("invalid_review_metadata_removed:review_status", report["warnings"])
        self.assertTrue(payload.workflow_graph.repair_report["repair_applied"])

    def test_action_without_outgoing_terminal_or_external_marker_blocks_v3_success(self) -> None:
        broken = copy.deepcopy(EMAIL_WORKFLOW_CANVAS)
        for node in broken["canvas"]["pages"][0]["nodes"]:
            if node.get("step_code") == "6.1":
                node["text"] = "6.1. CS ghi nhận thông tin nội bộ"
        broken["canvas"]["pages"][0]["edges"] = [
            edge for edge in broken["canvas"]["pages"][0]["edges"]
            if edge.get("from_step_code") != "6.1"
        ]

        _payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=broken,
            visual_context={},
        )

        self.assertIn("workflow_v3_action_missing_terminal_or_outgoing:6.1", report["blockers"])

    def test_summary_like_graph_blocks_v3_success(self) -> None:
        summary = {
            "document_metadata": {"title": "Email workflow"},
            "canvas": {
                "pages": [
                    {
                        "page": 1,
                        "nodes": [
                            {"id": "summary", "text": "Quy trình xác minh tài khoản qua email", "node_type": "action", "bbox": [1, 2, 3, 4]},
                        ],
                        "edges": [],
                    }
                ]
            },
        }

        _payload, report, _canvas = compile_workflow_v3_payload(
            filename="email_workflow.pdf",
            raw_text=RAW_TEXT,
            transcription=summary,
            visual_context={},
        )

        self.assertIn("workflow_v3_summary_like_graph_too_few_nodes", report["blockers"])


if __name__ == "__main__":
    unittest.main()
