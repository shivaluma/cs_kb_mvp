from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app import ranking
from app.ranking import (
    QueryUnderstanding,
    RankingOptions,
    SearchCandidate,
    business_rerank,
    load_ranking_config,
    maybe_model_rerank,
    normalize_query_understanding,
    seed_intent,
    should_use_model_rerank,
)


def candidate(
    chunk_id: str,
    chunk_type: str,
    text: str,
    *,
    title: str = "",
    score: float = 0.2,
    parent: str = "",
    status: str = "published",
    review_status: str = "approved",
    risk_level: str = "low",
    source_ref_quality: str = "block_id",
) -> SearchCandidate:
    return SearchCandidate(
        chunk_id=chunk_id,
        document_id="doc-1",
        document_version_id="version-1",
        parent_chunk_id=parent,
        title=title or chunk_id,
        normalized_title=ranking.normalize_text(title or chunk_id),
        content=text,
        retrieval_text=text,
        chunk_type=chunk_type,
        status=status,
        review_status=review_status,
        risk_level=risk_level,
        source_ref_quality=source_ref_quality,
        source_refs=({"block_id": f"block-{chunk_id}"},),
        meili_score=score,
        lexical_score=score,
        from_meilisearch=True,
        meili_rank=1,
    )


class SOPRankingPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        ranking._RERANK_CACHE.clear()
        ranking._QUERY_UNDERSTANDING_CACHE.clear()

    def test_exact_forbidden_phrase_ranks_direct_compliance_above_full_sop(self) -> None:
        rows = [
            candidate("full", "full_sop", "Toàn bộ quy định có nhắc ĐÓNG HỖ TRỢ TẠI ĐÂY.", score=0.9),
            candidate(
                "forbidden",
                "compliance_rule",
                "Tuyệt đối không nói ĐÓNG HỖ TRỢ TẠI ĐÂY cho case trùng.",
                title='Compliance rule: Không nói "ĐÓNG HỖ TRỢ TẠI ĐÂY"',
                score=0.7,
                risk_level="high",
            ),
        ]

        ranked = business_rerank(
            "đóng hỗ trợ tại đây",
            rows,
            RankingOptions(mode="portal_search", debug=True),
        )

        self.assertEqual(ranked[0].chunk_id, "forbidden")
        self.assertGreater(ranked[0].score_debug["boosts"]["exact_phrase"], 0)

    def test_wording_contrast_prefers_group_then_children(self) -> None:
        ranked = business_rerank(
            "khi nào dùng xin lỗi thay vì rất tiếc",
            [
                candidate("sorry", "wording_rule", 'Dùng "xin lỗi" khi lỗi do be, TX, nhà hàng.', score=0.6, parent="wording-group"),
                candidate("regret", "wording_rule", 'Dùng "rất tiếc" cho các trường hợp còn lại.', score=0.6, parent="wording-group"),
                candidate("group", "wording_rule_group", 'Phân biệt "xin lỗi" và "rất tiếc".', score=0.56),
            ],
            RankingOptions(mode="portal_search", debug=True),
        )

        self.assertEqual(ranked[0].chunk_id, "group")
        self.assertIn(ranked[1].chunk_id, {"sorry", "regret"})

    def test_handling_and_compliance_group_priorities(self) -> None:
        handling = business_rerank(
            "CS có được hỏi lại vấn đề khi khách đã nói trước đó không",
            [
                candidate("child", "handling_rule", "Nếu KH/TX đã đề cập vấn đề thì không hỏi lại.", score=0.62, parent="handling-group"),
                candidate("group", "handling_rule_group", "Nếu chưa đề cập thì hỏi; nếu đã đề cập thì không hỏi lại.", score=0.58),
            ],
            RankingOptions(mode="portal_search"),
        )
        compliance = business_rerank(
            "có được nói tài xế bị khóa vì vi phạm 3 lần không",
            [
                candidate("example", "example", "Ví dụ phản hồi về case khiếu nại.", score=0.7),
                candidate("group", "compliance_rule_group", "Không cung cấp ngưỡng hoặc lý do chế tài.", score=0.55, risk_level="high"),
            ],
            RankingOptions(mode="portal_search"),
        )

        self.assertEqual(handling[0].chunk_id, "group")
        self.assertEqual(compliance[0].chunk_id, "group")

    def test_portal_excludes_draft_but_admin_keeps_it(self) -> None:
        rows = [
            candidate("published", "handling_rule", "Published rule", status="published"),
            candidate("draft", "handling_rule", "Draft rule", status="draft", review_status="needs_review", score=0.9),
        ]

        portal = business_rerank("rule", rows, RankingOptions(mode="portal_search"))
        admin = business_rerank("rule", rows, RankingOptions(mode="admin_search"))

        self.assertEqual([item.chunk_id for item in portal], ["published"])
        self.assertIn("draft", [item.chunk_id for item in admin])

    def test_duplicate_parent_source_quality_and_examples_are_adjusted(self) -> None:
        ranked = business_rerank(
            "refund policy",
            [
                candidate("first", "policy_rule", "Refund policy", parent="same", source_ref_quality="table_row", score=0.4),
                candidate("second", "policy_rule", "Refund policy sibling", parent="same", source_ref_quality="block_id", score=0.4),
                candidate("example", "example", "Refund policy example", source_ref_quality="table_row", score=0.42),
            ],
            RankingOptions(mode="portal_search", debug=True),
        )

        self.assertEqual(ranked[0].chunk_id, "first")
        duplicate = next(item for item in ranked if item.chunk_id == "second")
        example = next(item for item in ranked if item.chunk_id == "example")
        self.assertIn("duplicate_parent", duplicate.score_debug["penalties"])
        self.assertIn("example_when_policy_exists", example.score_debug["penalties"])

    def test_config_change_affects_ranking_without_code_change(self) -> None:
        config = copy.deepcopy(load_ranking_config())
        config["chunk_type_priorities"]["generic"]["full_sop"] = 200
        ranked = business_rerank(
            "random browse",
            [
                candidate("atomic", "policy_rule", "Atomic policy", score=0.5),
                candidate("full", "full_sop", "Full document", score=0.1),
            ],
            RankingOptions(mode="admin_search"),
            config,
        )

        self.assertEqual(ranked[0].chunk_id, "full")

    def test_model_rerank_gating_and_failure_fallback(self) -> None:
        rows = [
            candidate("a", "handling_rule", "semantic candidate one", score=0.5),
            candidate("b", "handling_rule", "semantic candidate two", score=0.49),
            candidate("c", "handling_rule", "semantic candidate three", score=0.48),
        ]
        options = RankingOptions(
            mode="ai_chat",
            debug=True,
            query_understanding=QueryUnderstanding(intent="handling", confidence=0.8, source="model"),
        )
        with patch.object(ranking.settings, "rerank_provider", "llm"):
            business = business_rerank("khách đã nói vấn đề rồi CS nên xử lý thế nào", rows, options)
            decision = should_use_model_rerank("khách đã nói vấn đề rồi CS nên xử lý thế nào", business, options, load_ranking_config())
            self.assertTrue(decision["use"])
            with patch("app.ranking.rerank_with_provider", side_effect=TimeoutError("slow")):
                reranked, fallback = maybe_model_rerank("khách đã nói vấn đề rồi CS nên xử lý thế nào", business, options)
        self.assertEqual([item.chunk_id for item in reranked], [item.chunk_id for item in business])
        self.assertEqual(fallback["fallback"], "business_ranking")

    def test_exact_phrase_and_strong_gap_skip_model_rerank(self) -> None:
        options = RankingOptions(
            mode="ai_chat",
            debug=True,
            query_understanding=QueryUnderstanding(intent="forbidden_wording", confidence=0.9, source="seed"),
        )
        with patch.object(ranking.settings, "rerank_provider", "llm"):
            exact = business_rerank(
                "ĐÓNG HỖ TRỢ TẠI ĐÂY",
                [
                    candidate("forbidden", "compliance_rule", "Không nói ĐÓNG HỖ TRỢ TẠI ĐÂY.", title='Không nói "ĐÓNG HỖ TRỢ TẠI ĐÂY"', risk_level="high"),
                    candidate("other", "compliance_rule", "Không cung cấp quy trình nội bộ.", score=0.2),
                    candidate("full", "full_sop", "Full SOP.", score=0.1),
                ],
                options,
            )
            self.assertEqual(
                should_use_model_rerank("ĐÓNG HỖ TRỢ TẠI ĐÂY", exact, options, load_ranking_config())["skip_reason"],
                "strong_exact_phrase_top_result",
            )

    def test_rerank_cache_hit_avoids_provider_call(self) -> None:
        rows = business_rerank(
            "khách hỏi điều kiện xử lý trong trường hợp này thế nào",
            [
                candidate("a", "handling_rule", "candidate a", score=0.5),
                candidate("b", "handling_rule", "candidate b", score=0.49),
                candidate("c", "handling_rule", "candidate c", score=0.48),
            ],
            RankingOptions(mode="ai_chat", debug=True, query_understanding=QueryUnderstanding(intent="handling", confidence=0.8, source="model")),
        )
        options = RankingOptions(mode="ai_chat", debug=True, query_understanding=QueryUnderstanding(intent="handling", confidence=0.8, source="model"))
        with patch.object(ranking.settings, "rerank_provider", "llm"), patch("app.ranking.rerank_with_provider", return_value={"a": 0.2, "b": 0.9, "c": 0.1}) as provider:
            first, first_decision = maybe_model_rerank("khách hỏi điều kiện xử lý trong trường hợp này thế nào", rows, options)
            second, second_decision = maybe_model_rerank("khách hỏi điều kiện xử lý trong trường hợp này thế nào", rows, options)

        self.assertEqual(first[0].chunk_id, "b")
        self.assertEqual(second[0].chunk_id, "b")
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(first_decision["cache"], "miss")
        self.assertEqual(second_decision["cache"], "hit")

    def test_query_understanding_fallback_and_validation(self) -> None:
        seed = seed_intent("khi nào dùng xin lỗi")
        self.assertEqual(seed.intent, "wording")
        invalid = normalize_query_understanding({"intent": "invented", "confidence": 0.9}, QueryUnderstanding(intent="handling", confidence=0.7))
        self.assertEqual(invalid.intent, "handling")
        with patch.object(ranking.settings, "openrouter_api_key", "key"), patch("app.ranking.openrouter_chat_json", side_effect=ValueError("bad")):
            understood = ranking.understand_query("khi nào dùng xin lỗi", "ai_chat")
        self.assertEqual(understood.intent, "wording")
        self.assertTrue(any(warning.startswith("query_understanding_failed") for warning in understood.warnings))


if __name__ == "__main__":
    unittest.main()
