from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from app import repository
from app.schemas import RetrievalFilters


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

    def test_production_retrieval_requires_published_approved_structured_chunks(self) -> None:
        where_sql, params = repository.filter_sql(RetrievalFilters(status=["published"]))
        self.assertIn("d.current_version_id = v.id", where_sql)
        self.assertIn("COALESCE(c.metadata->>'review_status', '') = 'approved'", where_sql)
        self.assertIn("COALESCE(c.metadata->>'extraction_status', '') = ANY", where_sql)
        self.assertIn(["structured", "manually_curated"], params)
        self.assertIn("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'", where_sql)

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
