import unittest

from app.retrieval import rerank_by_query_intent


class RetrievalRankingTest(unittest.TestCase):
    def test_prohibition_query_boosts_source_warning_unit(self) -> None:
        rows = [
            {
                "chunk_id": "collect-info",
                "heading": "Xin thông tin chi tiết đơn hàng",
                "content": "Đối với đơn beFood: xin tên nhà hàng, món ăn, thời gian đặt đơn và Trip ID hoặc Order ID.",
                "section": "operational_instruction",
                "metadata": {"unit_type": "operational_instruction"},
                "score": 0.12,
                "lexical_score": 1.0,
                "vector_score": 0.2,
                "rank_source": ["lexical", "vector"],
                "best_rank": 1,
            },
            {
                "chunk_id": "security-note",
                "heading": "Lưu ý chung về cung cấp Order ID cho đơn beFood",
                "content": "Đối với đơn beFood có trạng thái hủy, CS không cung cấp Order ID cho KH. Nếu cung cấp QA chấm lỗi ZT.",
                "section": "operational_note",
                "metadata": {"unit_type": "operational_note", "risk_level": "high"},
                "score": 0.08,
                "lexical_score": 0.8,
                "vector_score": 0.2,
                "rank_source": ["lexical", "vector"],
                "best_rank": 2,
            },
        ]

        reranked = rerank_by_query_intent("khong cung cap order id befood", rows)

        self.assertEqual(reranked[0]["chunk_id"], "security-note")
        self.assertGreater(reranked[0]["score"], reranked[1]["score"])


if __name__ == "__main__":
    unittest.main()
