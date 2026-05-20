from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.answer_scope import AnswerScope, PolicyFacets, policy_applicability_debug
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
from app.openrouter import enforce_answer_grounding_contract, safe_json_dumps
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
        self.assertEqual(result["response"].retrieval_trace["error_message"], "boom")
        self.assertEqual(inserted_messages[0]["role"], "user")
        self.assertEqual(inserted_messages[1]["role"], "assistant")
        self.assertIn("Không thể tạo câu trả lời", inserted_messages[1]["content"])

    def test_grounded_prompt_metadata_json_handles_non_json_native_values(self) -> None:
        payload = {
            "score": Decimal("1.25"),
            "created_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
            "items": {Decimal("2.5")},
        }

        text = safe_json_dumps(payload)

        self.assertIn('"score": "1.25"', text)
        self.assertIn('"created_at": "2026-05-20 00:00:00+00:00"', text)
        self.assertIn('"2.5"', text)

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

    def test_narrow_contact_channel_query_penalizes_unasked_email_retry_branch(self) -> None:
        fallback = retrieval_result(
            "fallback",
            "handling_rule",
            score=0.78,
            heading="Khai thác rating 1 sao và cập nhật email",
            content=(
                "KH gửi rating 1 sao và complain thái độ TX thì CS call out để khai thác thêm thông tin. "
                "Nếu KH không có email, CS gọi tối thiểu 2 lần, cách nhau 10 phút để xin email cập nhật."
            ),
        )
        primary = retrieval_result(
            "primary",
            "handling_rule",
            score=0.72,
            heading="Kênh khai thác rating 1 sao",
            content="KH gửi rating 1 sao và complain thái độ TX thì CS liên hệ KH qua call out để khai thác thêm thông tin.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([fallback, primary]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH gửi rating 1 sao và complain thái độ TX, CS phải liên hệ qua kênh nào để khai thác thêm thông tin?",
                    limit=10,
                )
            )

        self.assertEqual(bundle.retrieval.results[0].chunk_id, "primary")
        excluded_debug = bundle.trace["excluded_candidate_debug"][0]
        self.assertEqual(excluded_debug["chunk_id"], "fallback")
        self.assertIn("email_missing", excluded_debug["negative_constraint_violations"])
        self.assertIn("retry_policy", excluded_debug["negative_constraint_violations"])

    def test_narrow_contact_channel_query_skips_parent_full_sop_context(self) -> None:
        direct = retrieval_result(
            "direct-channel",
            "handling_rule",
            score=0.8,
            heading="Kênh khai thác rating 1 sao",
            content="KH gửi rating 1 sao và complain thái độ TX thì CS liên hệ KH qua call out để khai thác thêm thông tin.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([direct]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]) as parent_rows,
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH gửi rating 1 sao và complain thái độ TX, CS phải liên hệ qua kênh nào để khai thác thêm thông tin?",
                    limit=10,
                )
            )

        parent_rows.assert_not_called()
        self.assertTrue(bundle.trace["parent_context_skipped_by_scope"])

    def test_grounded_chat_prunes_unasked_fallback_branch_from_answer(self) -> None:
        result = retrieval_result(
            "source",
            "handling_rule",
            score=0.84,
            heading="Kênh khai thác rating 1 sao",
            content=(
                "KH gửi rating 1 sao và complain thái độ TX thì CS liên hệ KH qua call out để khai thác thêm thông tin. "
                "Nếu KH không có email, CS gọi tối thiểu 2 lần, cách nhau 10 phút để xin email cập nhật."
            ),
        )
        retrieval = retrieval_response([result.model_copy(update={"metadata": {**result.metadata, "chat_source_role": "direct_sop"}})])
        bundle = ChatRetrievalBundle(
            retrieval=retrieval,
            source_groups=[{"role": "direct_sop", "label": "Direct SOP", "sources": [result.model_dump()]}],
            trace={"strategy": "chat_kb_index_multi_stage", "final_count": 1},
        )
        answer = GroundedAnswerPayload(
            answer=(
                "CS cần thực hiện call out để khai thác thêm thông tin. "
                "Nếu KH không có email, CS cần gọi tối thiểu 2 lần, cách nhau 10 phút để xin email cập nhật."
            ),
            steps=["Nếu KH không có email, gọi tối thiểu 2 lần cách nhau 10 phút."],
            warnings=[],
            confidence=0.86,
            source_indices=[1],
        )

        with (
            patch("app.chat.retrieve_for_chat", return_value=bundle),
            patch("app.chat.generate_grounded_answer", return_value=(answer, ["model_used"])),
            patch("app.chat.repository.unresolved_relations_for_chunks", return_value=[]),
            patch("app.chat.repository.log_chat"),
        ):
            response = grounded_chat(
                GroundedChatRequest(
                    question="KH gửi rating 1 sao và complain thái độ TX, CS phải liên hệ qua kênh nào để khai thác thêm thông tin?"
                )
            )

        self.assertEqual(response.answer, "CS cần thực hiện call out để khai thác thêm thông tin.")
        self.assertEqual(response.steps, [])
        self.assertIn("out_of_scope_branch_claim_removed:email_missing", response.warnings)
        self.assertIn("out_of_scope_branch_claim_removed:retry_policy", response.warnings)

    def test_policy_applicability_reranks_email_preference_over_email_after_call(self) -> None:
        post_call = retrieval_result(
            "post-call-email",
            "handling_rule",
            score=0.9,
            heading="Gửi kết quả xử lý qua email sau khi call",
            content="Sau khi call KH về kết quả tài chính beFood, CS gửi kết quả sau call qua email cho KH.",
        )
        missing_email = retrieval_result(
            "missing-email",
            "handling_rule",
            score=0.86,
            heading="KH không có email",
            content="Nếu KH không có email, CS gọi tối thiểu 2 lần cách nhau 10 phút để xin email cập nhật.",
        )
        direct_preference = retrieval_result(
            "email-preference",
            "policy_rule",
            score=0.62,
            heading="KH muốn email thay vì call",
            content="Khi KH chỉ muốn nhận phản hồi qua email thay vì call, CS kiểm tra rule kênh liên hệ được duyệt trước khi quyết định kênh phản hồi.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([post_call, missing_email, direct_preference]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH chỉ muốn nhận phản hồi qua email thay vì call thì xử lý sao?",
                    limit=10,
                )
            )

        self.assertEqual(bundle.retrieval.results[0].chunk_id, "email-preference")
        debug = {item["chunk_id"]: item for item in bundle.trace["candidate_debug"]}
        self.assertGreater(debug["email-preference"]["policy_applicability_score"], debug["post-call-email"]["policy_applicability_score"])
        self.assertIn("post_call_notification", debug["post-call-email"]["negative_constraint_violations"])

    def test_policy_applicability_uses_normalized_metadata_without_alias_text(self) -> None:
        post_call = retrieval_result(
            "post-call-email",
            "handling_rule",
            score=0.88,
            heading="Notification policy",
            content="CS sends the completed financial result notification to the customer.",
        ).model_copy(
            update={
                "metadata": {
                    "unit_type": "handling_rule",
                    "workflow_stage": "post_call_notification",
                    "channel_type": ["email"],
                    "review_status": "approved",
                }
            }
        )
        direct_metadata_rule = retrieval_result(
            "metadata-direct",
            "policy_rule",
            score=0.5,
            heading="Contact preference policy",
            content="Use the approved contact-preference decision rule for this case.",
        ).model_copy(
            update={
                "metadata": {
                    "unit_type": "policy_rule",
                    "workflow_stage": "contact_channel_selection",
                    "condition": ["email_instead_of_call"],
                    "channel_type": ["email", "call"],
                    "review_status": "approved",
                }
            }
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([post_call, direct_metadata_rule]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH chỉ muốn nhận phản hồi qua email thay vì call thì xử lý sao?",
                    limit=10,
                )
            )

        self.assertEqual(bundle.retrieval.results[0].chunk_id, "metadata-direct")
        debug = {item["chunk_id"]: item for item in bundle.trace["candidate_debug"]}
        self.assertIn("workflow_stage_match", debug["metadata-direct"]["selected_because"])
        self.assertIn("post_call_notification", debug["post-call-email"]["negative_constraint_violations"])

    def test_policy_applicability_accepts_unregistered_semantic_metadata_values(self) -> None:
        scope = AnswerScope(
            asked_fields=("full_workflow",),
            explicit_conditions=("vip_partner_case",),
            excluded_branch_types=(),
            is_narrow=False,
        )
        facets = PolicyFacets(
            asked_fields=scope.asked_fields,
            scenario_types=(),
            workflow_stages=("custom_partner_review",),
            negative_workflow_stages=(),
            explicit_conditions=("vip_partner_case",),
            channel_types=("zalo_support",),
            case_types=("partner_support",),
            actors=("CS",),
            unsupported_sensitive=False,
        )

        debug = policy_applicability_debug(
            query="custom partner review",
            candidate_text="Metadata-only policy unit",
            metadata={
                "unit_type": "policy_rule",
                "policy_semantics": {
                    "workflow_stage": "custom_partner_review",
                    "condition": ["vip_partner_case"],
                    "channel_type": ["zalo_support"],
                },
            },
            scope=scope,
            facets=facets,
            semantic_score=0.1,
            lexical_score=0.1,
        )

        self.assertEqual(debug["workflow_match_score"], 1.0)
        self.assertEqual(debug["condition_entailment_score"], 1.0)
        self.assertEqual(debug["action_alignment_score"], 1.0)
        self.assertIn("custom_partner_review", debug["candidate_policy_signals"]["workflow_stages"])
        self.assertIn("vip_partner_case", debug["candidate_policy_signals"]["conditions"])
        self.assertIn("zalo_support", debug["candidate_policy_signals"]["channel_types"])

    def test_scope_exclusion_uses_nested_branch_metadata_without_surface_text(self) -> None:
        fallback = retrieval_result(
            "metadata-fallback",
            "handling_rule",
            score=0.86,
            heading="Generic fallback",
            content="Fallback branch content.",
        ).model_copy(
            update={
                "metadata": {
                    "unit_type": "handling_rule",
                    "policy_semantics": {
                        "branch_type": ["retry_policy"],
                        "workflow_stage": "customer_response",
                    },
                }
            }
        )
        primary = retrieval_result(
            "metadata-primary",
            "policy_rule",
            score=0.52,
            heading="Generic contact channel",
            content="Primary contact channel rule.",
        ).model_copy(
            update={
                "metadata": {
                    "unit_type": "policy_rule",
                    "policy_semantics": {
                        "workflow_stage": "contact_channel_selection",
                        "channel_type": ["call"],
                    },
                }
            }
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([fallback, primary]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH cần CS liên hệ qua kênh nào?",
                    limit=10,
                )
            )

        self.assertEqual(bundle.retrieval.results[0].chunk_id, "metadata-primary")
        excluded_debug = bundle.trace["excluded_candidate_debug"][0]
        self.assertEqual(excluded_debug["chunk_id"], "metadata-fallback")
        self.assertIn("retry_policy", excluded_debug["negative_constraint_violations"])

    def test_unsupported_email_preference_scenario_stops_before_generation(self) -> None:
        post_call = retrieval_result(
            "post-call-email",
            "handling_rule",
            score=0.9,
            heading="Gửi kết quả xử lý qua email sau khi call",
            content="Sau khi call KH về kết quả tài chính beFood, CS gửi kết quả sau call qua email cho KH.",
        )
        image_flow = retrieval_result(
            "image-flow",
            "workflow_step",
            score=0.82,
            heading="KH gửi hình ảnh",
            content="KH gửi hình ảnh minh chứng qua email để CS kiểm tra theo luồng bổ sung chứng từ.",
        )
        missing_email = retrieval_result(
            "missing-email",
            "handling_rule",
            score=0.78,
            heading="KH không có email",
            content="Nếu KH không có email, CS gọi tối thiểu 2 lần cách nhau 10 phút để xin email cập nhật.",
        )
        rating_flow = retrieval_result(
            "rating-escalation",
            "escalation_rule",
            score=0.7,
            heading="Rating 1 sao complain thái độ TX",
            content="KH rating 1 sao complain thái độ TX thì CS call out khai thác thêm thông tin và chuyển escalation theo quy định.",
        )
        retrieval = retrieval_response(
            [
                item.model_copy(update={"metadata": {**item.metadata, "chat_source_role": "direct_sop"}})
                for item in [post_call, image_flow, missing_email, rating_flow]
            ]
        )
        bundle = ChatRetrievalBundle(
            retrieval=retrieval,
            source_groups=[{"role": "direct_sop", "label": "Direct SOP", "sources": [item.model_dump() for item in retrieval.results]}],
            trace={"strategy": "chat_kb_index_multi_stage", "final_count": 4},
        )

        with (
            patch("app.chat.retrieve_for_chat", return_value=bundle),
            patch("app.chat.generate_grounded_answer") as generate_answer,
            patch("app.chat.repository.log_chat"),
        ):
            response = grounded_chat(GroundedChatRequest(question="KH chỉ muốn nhận phản hồi qua email thay vì call thì xử lý sao?"))

        generate_answer.assert_not_called()
        self.assertIn("unsupported_scenario_detected", response.warnings)
        self.assertIn("no_primary_rule_for_customer_email_preference", response.retrieval_trace["unsupported_scenario"]["reason_codes"])
        self.assertIn("chưa có rule trực tiếp", response.answer)

    def test_context_debug_exposes_rerank_and_exclusion_reasons(self) -> None:
        direct = retrieval_result(
            "direct",
            "policy_rule",
            score=0.72,
            heading="Kênh khai thác rating 1 sao",
            content="KH gửi rating 1 sao và complain thái độ TX thì CS liên hệ KH qua call out để khai thác thêm thông tin.",
        )
        fallback = retrieval_result(
            "fallback",
            "handling_rule",
            score=0.7,
            heading="KH không có email",
            content="Nếu KH không có email, CS gọi tối thiểu 2 lần cách nhau 10 phút để xin email cập nhật.",
        )

        with (
            patch("app.chat.retrieve", side_effect=[retrieval_response([direct, fallback]), retrieval_response([])]),
            patch("app.chat.repository.approved_relation_target_rows_for_chunks", return_value=[]),
            patch("app.chat.repository.parent_sop_context_rows", return_value=[]),
        ):
            bundle = retrieve_for_chat(
                GroundedChatRequest(
                    question="KH gửi rating 1 sao và complain thái độ TX, CS phải liên hệ qua kênh nào để khai thác thêm thông tin?",
                    limit=10,
                )
            )

        selected_debug = bundle.trace["candidate_debug"][0]
        excluded_debug = bundle.trace["excluded_candidate_debug"][0]
        self.assertEqual(selected_debug["chunk_id"], "direct")
        self.assertEqual(excluded_debug["chunk_id"], "fallback")
        self.assertIn("email_missing", excluded_debug["negative_constraint_violations"])
        self.assertLess(excluded_debug["policy_applicability_score"], selected_debug["policy_applicability_score"])

    def test_answer_grounding_contract_rejects_risky_claim_source(self) -> None:
        risky = retrieval_result(
            "risky",
            "handling_rule",
            score=0.7,
            heading="Risky branch",
            content="Diagnostic context only.",
        ).model_copy(
            update={
                "metadata": {
                    "unit_type": "handling_rule",
                    "negative_constraint_violations": ["post_call_notification"],
                    "policy_applicability_score": 0.25,
                }
            }
        )
        answer = GroundedAnswerPayload(
            answer="Use this branch.",
            source_indices=[1],
            confidence=0.8,
            claim_grounding=[
                {
                    "claim": "Use this branch.",
                    "supported": True,
                    "relevant_to_question": True,
                    "source_indices": [1],
                    "scope": "in_scope",
                }
            ],
        )

        grounded, warnings = enforce_answer_grounding_contract(answer, retrieval_response([risky]))

        self.assertEqual(grounded.source_indices, [])
        self.assertEqual(grounded.confidence, 0)
        self.assertIn("claim_grounding_contract_rejected_answer", warnings)

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
