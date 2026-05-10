from __future__ import annotations

import unittest

from app import ingestion
from app.text_processing import chunk_text, spreadsheet_row_chunks, workflow_units_to_chunks


class ChunkingSemanticsTest(unittest.TestCase):
    def test_vietnamese_sentence_not_cut_mid_sentence(self) -> None:
        text = (
            "Quy định xử lý\n"
            "CS kiểm tra thông tin khách hàng trước khi xử lý yêu cầu. "
            "Nếu thông tin hợp lệ thì CS tiếp tục hỗ trợ theo quy trình."
        )

        chunks = chunk_text(text, target_tokens=8, overlap_tokens=0)

        self.assertTrue(any(chunk.content.endswith("yêu cầu.") for chunk in chunks))
        self.assertTrue(any(chunk.content.startswith("Nếu thông tin hợp lệ") for chunk in chunks))
        self.assertFalse(any(chunk.content.endswith("trước khi") for chunk in chunks))

    def test_bullet_list_not_split_mid_item(self) -> None:
        text = (
            "Checklist:\n"
            "- Kiểm tra số điện thoại, user ID và trạng thái tài khoản trước khi chuyển xử lý.\n"
            "- Ghi chú kết quả kiểm tra vào case."
        )

        chunks = chunk_text(text, target_tokens=6, overlap_tokens=0)

        first_item = "Kiểm tra số điện thoại, user ID và trạng thái tài khoản trước khi chuyển xử lý."
        self.assertTrue(any(first_item in chunk.content for chunk in chunks))
        self.assertFalse(any("Kiểm tra số điện thoại" in chunk.content and "trước khi chuyển xử lý." not in chunk.content for chunk in chunks))

    def test_condition_action_pair_stays_together(self) -> None:
        text = "Nếu khách hàng chưa xác minh được thông tin.\nThì CS cần xin thêm giấy tờ và chuyển Lead review."

        chunks = chunk_text(text, target_tokens=7, overlap_tokens=0)

        self.assertEqual(len(chunks), 1)
        self.assertIn("Nếu khách hàng", chunks[0].content)
        self.assertIn("Thì CS cần", chunks[0].content)

    def test_warning_note_attaches_to_previous_parent_rule(self) -> None:
        classification = type("Classification", (), {"document_type": "policy_rule", "source_type": "text_policy_rule", "confidence": 0.84})()
        chunks = ingestion.build_degraded_policy_text_draft(
            "policy.txt",
            "text/plain",
            "Nếu khách chưa xác minh thì CS cần kiểm tra lại.\nLưu ý: không cung cấp thông tin bảo mật.",
            [
                {"type": "line", "index": 0, "line_start": 1, "line_end": 1, "text": "Nếu khách chưa xác minh thì CS cần kiểm tra lại."},
                {"type": "line", "index": 1, "line_start": 2, "line_end": 2, "text": "Lưu ý: không cung cấp thông tin bảo mật."},
            ],
            classification,
            "openrouter_disabled",
        )
        normalized = ingestion.normalize_units(chunks)
        warning = next(chunk for chunk in normalized if chunk.metadata.get("unit_type") == "candidate_warning")

        self.assertTrue(warning.metadata.get("attached_to"))
        self.assertNotEqual(warning.metadata.get("attachment_status"), "needs_review_no_parent")

    def test_workflow_decision_keeps_yes_no_outcomes_in_one_unit(self) -> None:
        units = [
            {
                "unit_type": "decision_point",
                "title": "Kiểm tra thông tin",
                "content": "Nếu đủ thông tin: Yes -> xử lý tiếp. No -> xin thêm thông tin.",
                "metadata": {"outcomes": [{"condition": "yes"}, {"condition": "no"}]},
                "confidence": 0.9,
            }
        ]

        chunks = workflow_units_to_chunks(units, "Quy trình", "workflow.pdf")

        self.assertEqual(len(chunks), 1)
        self.assertIn("Yes", chunks[0].content)
        self.assertIn("No", chunks[0].content)
        self.assertEqual(chunks[0].metadata["outcomes"], [{"condition": "yes"}, {"condition": "no"}])

    def test_excel_row_stays_atomic(self) -> None:
        chunks = spreadsheet_row_chunks(
            0,
            "sheet",
            "Từ ngày 01.05.2025",
            2,
            [],
            ["Case A", "Nếu đủ điều kiện thì chuyển Tech. Lưu ý kiểm tra đầy đủ trước khi chuyển."],
            ["Case", "Action"],
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["row_number"], 2)
        self.assertIn("Nếu đủ điều kiện", chunks[0].content)
        self.assertIn("Lưu ý", chunks[0].content)


if __name__ == "__main__":
    unittest.main()
