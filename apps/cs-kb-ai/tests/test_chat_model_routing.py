from __future__ import annotations

import unittest

from app.chat import classify_chat_route, model_for_route
from app.schemas import GroundedChatRequest, RetrievalResponse


class ChatModelRoutingTest(unittest.TestCase):
    def test_simple_question_uses_simple_route(self) -> None:
        route, reason = classify_chat_route(GroundedChatRequest(question="SLA chat social là bao lâu?"), empty_retrieval())

        self.assertEqual(route, "simple")
        self.assertEqual(reason, "simple_factual_sop_qa")
        self.assertEqual(model_for_route(route), "google/gemini-2.5-flash-lite")

    def test_policy_exception_question_uses_policy_route(self) -> None:
        route, _reason = classify_chat_route(GroundedChatRequest(question="Khi nào cần chuyển xử lý cho Lead?"), empty_retrieval())

        self.assertEqual(route, "policy")

    def test_high_risk_question_uses_high_risk_route(self) -> None:
        route, _reason = classify_chat_route(GroundedChatRequest(question="Có được cung cấp Order ID cho khách không?"), empty_retrieval())

        self.assertEqual(route, "high_risk")
        self.assertEqual(model_for_route(route), "deepseek/deepseek-v3.2")

    def test_complex_macro_question_uses_complex_route(self) -> None:
        route, _reason = classify_chat_route(GroundedChatRequest(question="Soạn macro phản hồi thật gọn dựa trên các SOP này"), empty_retrieval())

        self.assertEqual(route, "complex")
        self.assertEqual(model_for_route(route), "moonshotai/kimi-k2.6")


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
