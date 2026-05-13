from __future__ import annotations

import unittest
from unittest.mock import patch

from app.chat import (
    ChatRetrievalBundle,
    contextual_retrieval_query,
    grounded_chat,
    has_policy_source,
    retrieve_for_chat,
    should_use_recent_context,
    updated_session_summary,
)
from app.schemas import Citation, GroundedChatRequest, RetrievalResponse, RetrievalResult


class ChatRetrievalTest(unittest.TestCase):
    def test_issue_router_match_expands_approved_target_sop(self) -> None:
        router = retrieval_result("router-chunk", "issue_router_unit", score=0.7)
        related_row = retrieval_row("target-chunk", "policy_rule", score=0.005, relation_type="requires")

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([]), retrieval_response([router])]) as retrieve,
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[related_row]) as relation_rows,
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(GroundedChatRequest(question="tao tasklist tech", limit=10))

        direct_filters = retrieve.call_args_list[0].args[0].filters
        index_filters = retrieve.call_args_list[1].args[0].filters
        self.assertIn("policy_rule", direct_filters.unit_types)
        self.assertIn("issue_router_unit", index_filters.unit_types)
        relation_rows.assert_called_once_with(["router-chunk"], ["router-chunk"], 5)
        self.assertEqual(
            [result.metadata["chat_source_role"] for result in bundle.retrieval.results],
            ["issue_router", "related_sop"],
        )
        self.assertTrue(has_policy_source(bundle.retrieval.results))
        self.assertEqual(bundle.source_groups[0]["role"], "issue_router")
        self.assertEqual(bundle.source_groups[1]["role"], "related_sop")

    def test_tool_and_action_context_without_sop_returns_conservative_answer(self) -> None:
        tool = retrieval_result("tool-chunk", "tool_link", score=0.6)
        action = retrieval_result("action-chunk", "quick_action_rule", score=0.5)
        retrieval = retrieval_response(
            [
                tool.model_copy(update={"metadata": {**tool.metadata, "chat_source_role": "tool_link"}}),
                action.model_copy(update={"metadata": {**action.metadata, "chat_source_role": "action_template"}}),
            ]
        )
        bundle = ChatRetrievalBundle(
            retrieval=retrieval,
            source_groups=[
                {"role": "tool_link", "label": "Tools", "sources": [tool.model_dump()]},
                {"role": "action_template", "label": "Action templates", "sources": [action.model_dump()]},
            ],
            trace={"strategy": "chat_kb_index_multi_stage", "final_count": 2},
        )

        with (
            patch("app.chat.retrieve_for_chat", return_value=bundle),
            patch("app.chat.generate_grounded_answer") as generate_answer,
            patch("app.chat.repository.log_chat"),
        ):
            response = grounded_chat(GroundedChatRequest(question="mo tool nao de tao case"))

        generate_answer.assert_not_called()
        self.assertIn("index_context_without_policy_source", response.warnings)
        self.assertEqual(response.confidence, 0.15)
        self.assertFalse(response.citations)

    def test_direct_sop_stays_before_parent_full_sop_context(self) -> None:
        direct = retrieval_result("direct-chunk", "policy_rule", score=0.8)
        parent_row = retrieval_row("parent-chunk", "full_sop", score=0.001)

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([direct]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[parent_row]),
        ):
            bundle = retrieve_for_chat(GroundedChatRequest(question="order id food", limit=10))

        self.assertEqual(
            [result.metadata["chat_source_role"] for result in bundle.retrieval.results],
            ["direct_sop", "parent_sop"],
        )
        self.assertEqual(bundle.retrieval.results[0].chunk_id, "direct-chunk")

    def test_session_context_only_expands_follow_up_queries(self) -> None:
        recent = ["Quy định xác minh tài khoản hotline là gì?"]

        self.assertTrue(should_use_recent_context("cái đó áp dụng cho chat social không?", recent))
        self.assertFalse(should_use_recent_context("Quy định hoàn tiền đơn food", recent))

        expanded = contextual_retrieval_query("vậy chat social thì sao", recent, "Scope: account verification")
        plain = contextual_retrieval_query("Quy định hoàn tiền đơn food", recent, "Scope: account verification")

        self.assertIn("Context for resolving references only", expanded)
        self.assertEqual(plain, "Quy định hoàn tiền đơn food")

    def test_session_summary_stays_short_and_intent_only(self) -> None:
        summary = updated_session_summary(
            "Previous intent: user compared hotline account verification.",
            "Hỏi tiếp về CIA và Chat Social",
            {"status": ["published"], "collections": ["account-verification"]},
        )

        self.assertLessEqual(len(summary), 600)
        self.assertIn("Latest user intent", summary)
        self.assertIn("account-verification", summary)


def retrieval_response(results: list[RetrievalResult]) -> RetrievalResponse:
    return RetrievalResponse(
        query="",
        normalized_query="",
        mode="hybrid",
        results=results,
        citations=[result.citation for result in results],
        warnings=[],
        latency_ms=0,
    )


def retrieval_result(chunk_id: str, unit_type: str, score: float = 0.5) -> RetrievalResult:
    row = retrieval_row(chunk_id, unit_type, score=score)
    citation = Citation(
        document_id=row["document_id"],
        version_id=row["version_id"],
        chunk_id=row["chunk_id"],
        chunk_index=row["chunk_index"],
        section=row["section"],
        title=row["title"],
        version_number=row["version_number"],
        source_filename=row["source_filename"],
    )
    return RetrievalResult(
        document_id=citation.document_id,
        version_id=citation.version_id,
        chunk_id=citation.chunk_id,
        title=citation.title,
        source_filename=citation.source_filename,
        version_number=citation.version_number,
        chunk_index=citation.chunk_index,
        section=citation.section,
        heading=row["heading"],
        content=row["content"],
        score=row["score"],
        lexical_score=row["lexical_score"],
        vector_score=row["vector_score"],
        rank_source=row["rank_source"],
        metadata=row["metadata"],
        citation=citation,
    )


def retrieval_row(chunk_id: str, unit_type: str, score: float = 0.5, relation_type: str | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "unit_type": unit_type,
        "review_status": "approved",
        "extraction_status": "structured",
    }
    if relation_type:
        metadata["relation_type"] = relation_type
    return {
        "chunk_id": chunk_id,
        "document_id": f"doc-{chunk_id}",
        "version_id": f"version-{chunk_id}",
        "title": f"Title {chunk_id}",
        "source_filename": f"{chunk_id}.md",
        "version_number": 1,
        "chunk_index": 0,
        "section": unit_type,
        "heading": f"Heading {chunk_id}",
        "content": f"Content for {chunk_id}",
        "score": score,
        "lexical_score": score,
        "vector_score": 0.0,
        "rank_source": ["lexical"],
        "metadata": metadata,
    }


if __name__ == "__main__":
    unittest.main()
