from __future__ import annotations

import unittest

from app.search_labels import embedding_text_for_unit, is_bad_search_label, meaningful_search_label


class SearchLabelTest(unittest.TestCase):
    def test_numeric_heading_is_replaced_with_step_label(self) -> None:
        label = meaningful_search_label("5", "5. Xử lý theo quy trình/quy định tương ứng", "workflow_step")

        self.assertEqual(label, "Bước 5: Xử lý theo quy trình/quy định tương ứng")
        self.assertTrue(is_bad_search_label("5", "5. Xử lý theo quy trình/quy định tương ứng"))

    def test_duplicate_heading_is_replaced_with_decision_label(self) -> None:
        label = meaningful_search_label("Đủ thông tin để xử lý?", "Đủ thông tin để xử lý?", "decision_point")

        self.assertEqual(label, "Điều kiện: Đủ thông tin để xử lý?")
        self.assertTrue(is_bad_search_label("Đủ thông tin để xử lý?", "Đủ thông tin để xử lý?"))

    def test_meaningful_short_heading_is_kept(self) -> None:
        label = meaningful_search_label("Outbound call không thành công", "10.2. Gửi mail cho A thông báo Be đã liên hệ không thành công", "policy_rule")

        self.assertEqual(label, "Outbound call không thành công")

    def test_embedding_uses_generated_label_instead_of_bad_heading(self) -> None:
        text = embedding_text_for_unit("5", "5. Xử lý theo quy trình/quy định tương ứng", "workflow_step")

        self.assertIn("Bước 5:", text)
        self.assertNotIn("5 5.", text)


if __name__ == "__main__":
    unittest.main()
