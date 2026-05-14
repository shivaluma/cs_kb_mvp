from __future__ import annotations

import unittest
from unittest.mock import patch

from app.chat import (
    ChatRetrievalBundle,
    assistant_context_briefs,
    assistant_context_chunk_ids,
    contextual_retrieval_query,
    evidence_confidence,
    grounded_chat,
    grounded_chat_session_message,
    has_policy_source,
    retrieve_for_chat,
    should_use_recent_context,
    updated_session_summary,
)
from app.schemas import (
    ChatSessionCreateRequest,
    ChatSessionMessageRequest,
    ChatSessionUpdateRequest,
    Citation,
    GroundedAnswerPayload,
    GroundedChatRequest,
    RetrievalResponse,
    RetrievalResult,
)


class ChatRetrievalTest(unittest.TestCase):
    def test_session_message_returns_fallback_when_generation_raises(self) -> None:
        session = {
            "id": "session-1",
            "title": "Existing chat",
            "summary": "",
            "status": "active",
            "message_count": 2,
            "model_route": "simple",
            "filters": {},
        }
        inserted_messages: list[dict[str, object]] = []

        def fake_insert_message(session_id: str, role: str, content: str, **kwargs: object) -> dict[str, object]:
            message = {
                "id": f"{role}-{len(inserted_messages)}",
                "session_id": session_id,
                "role": role,
                "content": content,
                "response_payload": kwargs.get("response_payload") or {},
                "source_chunk_ids": kwargs.get("source_chunk_ids") or [],
                "token_context_metadata": kwargs.get("token_context_metadata") or {},
                "created_at": "2026-05-14T00:00:00Z",
            }
            inserted_messages.append(message)
            return message

        with (
            patch("app.chat.repository.chat_session_by_id", return_value=session),
            patch("app.chat.repository.recent_chat_user_messages", return_value=["previous question"]),
            patch("app.chat.repository.recent_chat_assistant_messages", return_value=[]),
            patch("app.chat.repository.insert_chat_message", side_effect=fake_insert_message),
            patch("app.chat.repository.update_chat_session_after_assistant", return_value={**session, "message_count": 4}),
            patch("app.chat.grounded_chat", side_effect=RuntimeError("boom")),
        ):
            result = grounded_chat_session_message(
                "session-1",
                ChatSessionMessageRequest(question="tiếp theo xử lý sao?"),
            )

        self.assertEqual(result["response"].confidence, 0)
        self.assertIn("chat_session_generation_failed:RuntimeError", result["response"].warnings)
        self.assertEqual(inserted_messages[0]["role"], "user")
        self.assertEqual(inserted_messages[1]["role"], "assistant")
        self.assertIn("Không thể tạo câu trả lời", inserted_messages[1]["content"])

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

    def test_condition_rerank_penalizes_wrong_boundary_context(self) -> None:
        si_lock = retrieval_result(
            "si-lock",
            "handling_rule",
            score=0.8,
            heading="Xử lý TX bị khóa bởi SI yêu cầu gọi số khác",
            content="Trường hợp TX bị khóa bởi SI liên hệ yêu cầu Be liên hệ qua SĐT khác thì kiểm tra lý do khóa theo case ID.",
        )
        outbound = retrieval_result(
            "outbound",
            "handling_rule",
            score=0.72,
            heading="Xử lý KH/TX yêu cầu gọi số khác",
            content="Nếu CS liên hệ TX để xử lý vấn đề do KH phản ánh nhưng TX yêu cầu CS gọi ra 1 số khác thì CS liên hệ SĐT TX cung cấp để xử lý tiếp.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([si_lock, outbound]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(GroundedChatRequest(question="CS gọi TX để xử lý phản ánh từ KH, TX yêu cầu gọi sang số khác thì sao?", limit=10))

        self.assertEqual(bundle.retrieval.results[0].chunk_id, "outbound")
        self.assertIn("si_lock_not_asked", bundle.retrieval.results[1].metadata["chat_match_penalties"])

    def test_semantic_duplicate_chunks_merge_before_context(self) -> None:
        first = retrieval_result(
            "policy",
            "handling_rule",
            score=0.62,
            heading="Xử lý yêu cầu TX trên Hotline 1900232345",
            content="TX liên hệ hỗ trợ qua Hotline 1900232345, CS hướng dẫn TX liên hệ lại đúng kênh hỗ trợ hoặc gửi mail đến hộp thư hotro@be.com.vn.",
        )
        duplicate = retrieval_result(
            "workflow",
            "workflow_step",
            score=0.6,
            heading="Xử lý yêu cầu TX trên Hotline",
            content="Đối với TX liên hệ qua Hotline 1900232345, CS hướng dẫn TX liên hệ lại đúng kênh hỗ trợ hoặc gửi mail đến hộp thư hotro@be.com.vn.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([first, duplicate]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(GroundedChatRequest(question="TX liên hệ Hotline 1900232345 để được hỗ trợ thì xử lý sao?", limit=10))

        self.assertEqual(len(bundle.retrieval.results), 1)
        self.assertEqual(bundle.retrieval.results[0].chunk_id, "policy")
        self.assertEqual(bundle.retrieval.results[0].metadata["chat_dedupe_status"], "semantic_duplicates_merged")

    def test_evidence_confidence_caps_single_policy_citation(self) -> None:
        result = retrieval_result(
            "single",
            "handling_rule",
            score=0.2,
            heading="Xử lý KH/TX yêu cầu gọi số khác",
            content="Nếu CS liên hệ TX để xử lý vấn đề do KH phản ánh nhưng TX yêu cầu CS gọi ra 1 số khác thì CS liên hệ SĐT TX cung cấp.",
        )
        confidence = evidence_confidence(
            "CS gọi TX để xử lý phản ánh từ KH, TX yêu cầu gọi sang số khác thì sao?",
            [result],
            [result],
            model_confidence=1.0,
            has_unresolved_dependency=False,
        )

        self.assertLess(confidence, 1.0)
        self.assertLessEqual(confidence, 0.82)

    def test_grounded_chat_overrides_model_confidence(self) -> None:
        result = retrieval_result(
            "source",
            "handling_rule",
            score=0.21,
            heading="Xử lý yêu cầu TX trên Hotline",
            content="TX liên hệ hỗ trợ qua Hotline 1900232345, CS hướng dẫn TX liên hệ đúng kênh hoặc gửi mail.",
        )
        retrieval = retrieval_response([result.model_copy(update={"metadata": {**result.metadata, "chat_source_role": "direct_sop"}})])
        bundle = ChatRetrievalBundle(
            retrieval=retrieval,
            source_groups=[{"role": "direct_sop", "label": "Direct SOP", "sources": [result.model_dump()]}],
            trace={"strategy": "chat_kb_index_multi_stage", "final_count": 1},
        )
        answer = GroundedAnswerPayload(answer="Hướng dẫn TX liên hệ đúng kênh hoặc gửi mail.", steps=[], warnings=[], confidence=1.0, source_indices=[1])

        with (
            patch("app.chat.retrieve_for_chat", return_value=bundle),
            patch("app.chat.generate_grounded_answer", return_value=(answer, ["model_used"])),
            patch("app.chat.repository.unresolved_relations_for_chunks", return_value=[]),
            patch("app.chat.repository.log_chat"),
        ):
            response = grounded_chat(GroundedChatRequest(question="TX liên hệ Hotline 1900232345 để được hỗ trợ thì xử lý sao?"))

        self.assertLess(response.confidence, 1.0)
        self.assertIn("model_confidence_overridden_by_evidence_score", response.warnings)

    def test_session_context_only_expands_follow_up_queries(self) -> None:
        recent = ["Quy định xác minh tài khoản hotline là gì?"]

        self.assertTrue(should_use_recent_context("cái đó áp dụng cho chat social không?", recent))
        self.assertFalse(should_use_recent_context("Quy định hoàn tiền đơn food", recent))

        expanded = contextual_retrieval_query("vậy chat social thì sao", recent, "Scope: account verification")
        plain = contextual_retrieval_query("Quy định hoàn tiền đơn food", recent, "Scope: account verification")

        self.assertIn("Follow-up context for retrieval only", expanded)
        self.assertEqual(plain, "Quy định hoàn tiền đơn food")

    def test_follow_up_query_uses_previous_assistant_brief(self) -> None:
        expanded = contextual_retrieval_query(
            "rồi làm gì tiếp",
            ["KH/TX liên hệ qua email hotro thì hỗ trợ làm sao"],
            "Scope: account verification",
            ["Nếu KH/TX cung cấp được thông tin, CS sẽ gọi ra xác minh thông tin. Sau đó hỗ trợ theo quy trình tương ứng."],
        )

        self.assertIn("gọi ra xác minh thông tin", expanded)
        self.assertIn("Follow-up context for retrieval only", expanded)

    def test_assistant_context_brief_extracts_steps_and_source_ids(self) -> None:
        rows = [
            {
                "content": "fallback",
                "source_chunk_ids": ["chunk-a"],
                "response_payload": {
                    "answer": "Workflow email.",
                    "steps": ["B1 kiểm tra email", "B2 gọi ra xác minh"],
                    "citations": [{"chunk_id": "chunk-b", "title": "Email SOP"}],
                },
            }
        ]

        self.assertIn("B2 gọi ra xác minh", assistant_context_briefs(rows)[0])
        self.assertEqual(assistant_context_chunk_ids(rows), ["chunk-a", "chunk-b"])

    def test_follow_up_reuses_previous_cited_chunks_as_context_sources(self) -> None:
        generic = retrieval_result(
            "generic",
            "handling_rule",
            score=0.45,
            heading="Đối với kênh Call In App, Mail In App, Chat",
            content="Không cần xác minh thông tin người liên hệ.",
        )
        previous_source_row = retrieval_row(
            "prev-workflow",
            "workflow_step",
            score=0.32,
            heading="Gọi ra xác minh thông tin",
            content="Nếu KH/TX cung cấp được thông tin, CS sẽ gọi ra xác minh thông tin và tiếp tục xử lý theo quy trình tương ứng.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([generic]), retrieval_response([])]),
            patch("app.chat.repository.published_chunk_rows_by_ids", return_value=[previous_source_row]) as context_rows,
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="CS sẽ gọi ra xác minh thông tin rồi làm gì tiếp",
                    retrieval_query="CS sẽ gọi ra xác minh thông tin rồi làm gì tiếp\nFollow-up context: gọi ra xác minh thông tin",
                    context_chunk_ids=["prev-workflow"],
                    limit=10,
                )
            )

        context_rows.assert_called_once()
        self.assertEqual(bundle.retrieval.results[0].chunk_id, "prev-workflow")
        self.assertEqual(bundle.retrieval.results[0].metadata["chat_retrieval_reason"], "session_context_source")

    def test_session_summary_stays_short_and_intent_only(self) -> None:
        summary = updated_session_summary(
            "Previous intent: user compared hotline account verification.",
            "Hỏi tiếp về CIA và Chat Social",
            {"status": ["published"], "collections": ["account-verification"]},
        )

        self.assertLessEqual(len(summary), 600)
        self.assertIn("Latest user intent", summary)
        self.assertIn("account-verification", summary)

    def test_blank_model_route_defaults_for_legacy_clients(self) -> None:
        self.assertEqual(ChatSessionCreateRequest(model_route="").model_route, "simple")
        self.assertEqual(ChatSessionMessageRequest(question="hello", model_route="").model_route, "simple")
        self.assertEqual(GroundedChatRequest(question="hello", model_route="").model_route, "simple")
        self.assertIsNone(ChatSessionUpdateRequest(model_route="").model_route)


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


def retrieval_result(
    chunk_id: str,
    unit_type: str,
    score: float = 0.5,
    heading: str | None = None,
    content: str | None = None,
) -> RetrievalResult:
    row = retrieval_row(chunk_id, unit_type, score=score, heading=heading, content=content)
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


def retrieval_row(
    chunk_id: str,
    unit_type: str,
    score: float = 0.5,
    relation_type: str | None = None,
    heading: str | None = None,
    content: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "unit_type": unit_type,
        "review_status": "approved",
        "extraction_status": "structured",
    }
    if relation_type:
        metadata["relation_type"] = relation_type
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-shared" if chunk_id in {"policy", "workflow"} else f"doc-{chunk_id}",
        "version_id": "version-shared" if chunk_id in {"policy", "workflow"} else f"version-{chunk_id}",
        "title": f"Title {chunk_id}",
        "source_filename": f"{chunk_id}.md",
        "version_number": 1,
        "chunk_index": 0,
        "section": unit_type,
        "heading": heading or f"Heading {chunk_id}",
        "content": content or f"Content for {chunk_id}",
        "score": score,
        "lexical_score": score,
        "vector_score": 0.0,
        "rank_source": ["lexical"],
        "metadata": metadata,
    }


if __name__ == "__main__":
    unittest.main()
