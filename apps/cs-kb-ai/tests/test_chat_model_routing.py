from __future__ import annotations

import unittest

from app.chat import model_for_route, select_chat_model
from app.schemas import GroundedChatRequest, RetrievalResponse


class ChatModelRoutingTest(unittest.TestCase):
    def test_default_question_uses_simple_gemini_route(self) -> None:
        selection = select_chat_model(GroundedChatRequest(question="Có được cung cấp Order ID cho khách không?"), empty_retrieval())

        self.assertEqual(selection.route, "simple")
        self.assertEqual(selection.reason, "manual_route")
        self.assertEqual(selection.model, "google/gemini-2.5-flash-lite")
        self.assertFalse(selection.strict_grounding)

    def test_legacy_auto_request_is_coerced_to_simple(self) -> None:
        selection = select_chat_model(GroundedChatRequest(question="Khi nào cần chuyển xử lý cho Lead?", model_route="auto"), empty_retrieval())

        self.assertEqual(selection.route, "simple")
        self.assertEqual(selection.reason, "auto_route_disabled_simple_default")
        self.assertEqual(selection.model, "google/gemini-2.5-flash-lite")

    def test_manual_policy_route_still_uses_kimi(self) -> None:
        selection = select_chat_model(GroundedChatRequest(question="Khi nào cần chuyển xử lý cho Lead?", model_route="policy"), empty_retrieval())

        self.assertEqual(selection.route, "policy")
        self.assertEqual(selection.model, "moonshotai/kimi-k2.5")
        self.assertTrue(selection.strict_grounding)

    def test_manual_complex_route_still_uses_kimi_26(self) -> None:
        selection = select_chat_model(GroundedChatRequest(question="Soạn macro phản hồi thật gọn", model_route="complex"), empty_retrieval())

        self.assertEqual(selection.route, "complex")
        self.assertEqual(model_for_route(selection.route), "moonshotai/kimi-k2.6")
        self.assertEqual(selection.model, "moonshotai/kimi-k2.6")


def empty_retrieval() -> RetrievalResponse:
    return RetrievalResponse(
        query="",
        normalized_query="",
        mode="hybrid",
        results=[],
        citations=[],
        warnings=[],
        latency_ms=0,
    )


if __name__ == "__main__":
    unittest.main()
