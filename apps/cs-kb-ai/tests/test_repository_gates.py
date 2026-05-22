from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import repository
from app.schemas import DocumentMetadata, ExtractionUnitUpdateRequest, RetrievalFilters, SourceRef


class RepositoryGateTest(unittest.TestCase):
    def test_degraded_unit_requires_manual_curation(self) -> None:
        self.assertTrue(
            repository.is_degraded_unconverted(
                {
                    "extraction_status": "degraded",
                    "review_status": "approved",
                    "manual_curation_status": "",
                }
            )
        )
        self.assertFalse(
            repository.is_degraded_unconverted(
                {
                    "extraction_status": "manually_curated",
                    "review_status": "approved",
                    "manual_curation_status": "converted",
                }
            )
        )

    def test_rejected_extraction_unit_status_is_valid_but_not_publish_ready(self) -> None:
        request = ExtractionUnitUpdateRequest(
            title="Noise unit",
            content="Duplicate or incorrect extracted content.",
            unit_type="policy_rule",
            confidence=0.2,
            review_status="rejected",
            metadata={},
            actor="cs-ops-ui",
        )

        self.assertEqual(request.review_status, "rejected")
        self.assertFalse(repository.is_reviewed_status("rejected"))

    def test_production_retrieval_requires_published_approved_structured_chunks(self) -> None:
        where_sql, params = repository.filter_sql(RetrievalFilters(status=["published"]))
        self.assertIn("d.current_version_id = v.id", where_sql)
        self.assertIn("v.publish_state = 'published_ready'", where_sql)
        self.assertIn("COALESCE(c.metadata->>'review_status', '') = 'approved'", where_sql)
        self.assertIn("COALESCE(c.metadata->>'extraction_status', '') = ANY", where_sql)
        self.assertIn(["structured", "manually_curated"], params)
        self.assertIn("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'", where_sql)

    def test_policy_table_requires_structured_table_or_sheet_refs(self) -> None:
        self.assertFalse(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "text", "line_start": 1, "line_end": 2}]},
            )
        )
        self.assertTrue(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "docx_table", "table_index": 0, "row_index": 1, "column_names": ["Case", "Action"]}]},
            )
        )
        self.assertTrue(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "excel", "sheet": "Rules", "row_start": 2, "row_end": 2}]},
            )
        )

    def test_enterprise_metadata_and_source_ref_anchor_fields_are_first_class(self) -> None:
        metadata = DocumentMetadata(
            owner_team="CS Ops",
            visibility="customer_facing",
            scope="cs_response",
            policy_type="communication_rule",
            authority_level="source_of_truth",
            related_sop_ids=["sop-refund"],
            conflict_group="refund-customer-wording",
            effective_to="2026-12-31",
        )
        source_ref = SourceRef(
            source_type="pdf",
            source_file="policy.pdf",
            block_id="block-7",
            page_number=3,
            sheet_name="Rules",
            row=12,
            column="Action",
        )

        self.assertEqual(metadata.visibility, "customer_facing")
        self.assertEqual(metadata.scope, "cs_response")
        self.assertEqual(metadata.policy_type, "communication_rule")
        self.assertEqual(metadata.authority_level, "source_of_truth")
        self.assertEqual(metadata.related_sop_ids, ["sop-refund"])
        self.assertEqual(metadata.conflict_group, "refund-customer-wording")
        self.assertEqual(metadata.effective_to, "2026-12-31")
        self.assertEqual(source_ref.block_id, "block-7")
        self.assertEqual(source_ref.page_number, 3)
        self.assertEqual(source_ref.sheet_name, "Rules")
        self.assertEqual(source_ref.row, 12)
        self.assertEqual(source_ref.column, "Action")

    def test_effective_heading_sql_escapes_literal_percent_for_psycopg3(self) -> None:
        self.assertIn("|| '%%'", repository.EFFECTIVE_HEADING_SQL)
        self.assertNotIn("|| '%'", repository.EFFECTIVE_HEADING_SQL)

    def test_feedback_triage_helpers_prioritize_operational_risk(self) -> None:
        self.assertTrue(repository.is_uuid_text("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
        self.assertFalse(repository.is_uuid_text("legacy-sop-code"))
        self.assertEqual(repository.feedback_severity("wrong"), "high")
        self.assertEqual(repository.feedback_severity("outdated"), "high")
        self.assertEqual(repository.feedback_severity("missing_step"), "high")
        self.assertEqual(repository.feedback_severity("need_macro"), "medium")
        self.assertIn("draft version", repository.suggested_feedback_action("outdated"))
        self.assertIn("retrieval", repository.suggested_feedback_action("search_result_wrong"))
        self.assertEqual(repository.median_from_sorted([1000, 3000, 9000]), 3000)
        self.assertEqual(repository.median_from_sorted([1000, 5000]), 3000)

    def test_chat_logging_persists_retrieval_trace_for_debugging(self) -> None:
        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.sql = sql
                self.params = params

        fake_connection = FakeConnection()
        response = SimpleNamespace(
            question="Can CS say this?",
            answer="Use source only.",
            citations=[SimpleNamespace(chunk_id="chunk-1")],
            confidence=0.7,
            warnings=["grounded"],
            retrieval_trace={"authority_analysis": {"answer_allowed": True}},
            model_route="policy",
            model_used="moonshotai/kimi-k2.5",
            model_reason="manual_route",
            latency_ms=25,
        )

        with patch("app.repository.connection", return_value=fake_connection):
            repository.log_chat(response)

        self.assertIn("retrieval_trace", fake_connection.sql)
        self.assertIn("model_route", fake_connection.sql)
        self.assertIn('"answer_allowed": true', str(fake_connection.params))
        self.assertIn("policy", fake_connection.params)

    def test_admin_reset_preserves_curated_search_taxonomy(self) -> None:
        self.assertIn("ai_chunks", repository.ADMIN_RESET_TABLES)
        self.assertIn("ai_chat_sessions", repository.ADMIN_RESET_TABLES)
        self.assertIn("search_synonym_suggestions", repository.ADMIN_RESET_TABLES)
        self.assertNotIn("search_synonym_groups", repository.ADMIN_RESET_TABLES)
        self.assertIn("search_synonym_groups", repository.ADMIN_RESET_PRESERVED_TABLES)
        counts = {table: 1 for table in repository.ADMIN_RESET_TABLES}
        grouped = repository.group_counts(counts)
        self.assertGreater(grouped["knowledge_base"], 0)
        self.assertGreater(grouped["chat"], 0)

    def test_force_approve_promotes_candidate_unit_types(self) -> None:
        self.assertEqual(repository.promoted_unit_type("candidate_rule", "policy_rule"), "policy_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_table_row", "policy_table"), "policy_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_step", "workflow_diagram"), "workflow_step")
        self.assertEqual(repository.promoted_unit_type("candidate_action", "workflow_diagram"), "workflow_step")
        self.assertEqual(repository.promoted_unit_type("candidate_decision", "workflow_diagram"), "decision_point")
        self.assertEqual(repository.promoted_unit_type("candidate_sla", "workflow_diagram"), "sla_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_audit_rule", "workflow_diagram"), "warning")
        self.assertEqual(repository.promoted_unit_type("candidate_queue_rule", "workflow_diagram"), "routing_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_workflow_text", "workflow_diagram"), "workflow_overview")
        self.assertEqual(repository.promoted_unit_type("candidate_section", "policy_rule"), "text_section")
        self.assertEqual(repository.promoted_unit_type("full_sop", "policy_rule"), "full_sop")

    def test_related_document_chunk_creates_unresolved_relation_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-1",
                "section": "related_document",
                "heading": "Quy định sử dụng tasklist",
                "content": "bat buoc xem truoc khi xu ly task.",
                "metadata": {"unit_type": "related_document"},
            },
            repository.normalize_phrase("Quy định chuyển Tech"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "Quy định sử dụng tasklist")
        self.assertEqual(candidates[0]["relation_type"], "requires")

    def test_explicit_text_reference_creates_single_requires_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-2",
                "section": "policy_rule",
                "heading": "Tasklist",
                "content": "CS thực hiện theo Quy định sử dụng tasklist trước khi xử lý.",
                "metadata": {"unit_type": "policy_rule"},
            },
            repository.normalize_phrase("Quy định chuyển Tech"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "Quy định sử dụng tasklist")
        self.assertEqual(candidates[0]["relation_type"], "requires")
        self.assertEqual(candidates[0]["metadata"]["relation_source"], "explicit_text_reference")
        self.assertFalse(candidates[0]["metadata"]["needs_clarification"])

    def test_ambiguous_corresponding_process_creates_clarification_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-3",
                "section": "handling_rule",
                "heading": "Hỗ trợ khách hàng",
                "content": "CS hỗ trợ theo quy trình tương ứng.",
                "metadata": {"unit_type": "handling_rule"},
            },
            repository.normalize_phrase("Quy định xác minh tài khoản"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "quy trình tương ứng")
        self.assertEqual(candidates[0]["relation_type"], "requires")
        self.assertTrue(candidates[0]["metadata"]["needs_clarification"])

    def test_operational_handoff_creates_routes_to_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-4",
                "section": "workflow_step",
                "heading": "Chuyển case",
                "content": "CS cần chuyển cho MSC trong vòng 30 phút.",
                "metadata": {"unit_type": "workflow_step"},
            },
            repository.normalize_phrase("Quy định theo dõi hình ảnh"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "MSC")
        self.assertEqual(candidates[0]["relation_type"], "routes_to")
        self.assertEqual(candidates[0]["metadata"]["relation_source"], "operational_handoff")

    def test_manual_relation_types_are_preserved(self) -> None:
        self.assertEqual(repository.normalize_relation_type("must_follow"), "must_follow")
        self.assertEqual(repository.normalize_relation_type("uses_macro"), "uses_macro")
        self.assertEqual(repository.normalize_relation_type("related_to"), "related_to")
        self.assertEqual(repository.normalize_relation_type("possible_conflict"), "possible_conflict")

    def test_high_risk_governance_requires_owner_review_sla_and_future_due_date(self) -> None:
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        failures = repository.high_risk_governance_failures(
            {"risk_level": "high"},
            {},
            "payment compliance rule",
            "policy_rule",
        )

        self.assertIn("missing_owner_team", failures)
        self.assertIn("missing_review_frequency", failures)
        self.assertIn("missing_last_reviewed_at", failures)
        self.assertIn("missing_next_review_due", failures)

        ready_failures = repository.high_risk_governance_failures(
            {
                "risk_level": "high",
                "owner_team": "CS Ops",
                "review_frequency": "quarterly",
                "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
                "next_review_due": tomorrow,
            },
            {},
            "payment compliance rule",
            "policy_rule",
        )
        self.assertEqual(ready_failures, [])

    def test_high_risk_governance_blocks_overdue_review(self) -> None:
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        failures = repository.high_risk_governance_failures(
            {
                "risk_level": "critical",
                "owner_team": "CS Ops",
                "review_frequency": "annual",
                "last_reviewed_at": "2026-01-01",
                "next_review_due": yesterday,
            },
            {},
            "security rule",
            "policy_rule",
        )

        self.assertEqual(failures, ["high_risk_review_due_in_past"])


if __name__ == "__main__":
    unittest.main()
