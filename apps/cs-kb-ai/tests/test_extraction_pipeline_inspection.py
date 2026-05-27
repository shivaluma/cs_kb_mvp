from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.main import build_extraction_pipeline_inspection, build_reduce_reconcile_report
from app.schemas import ExtractionPipelineInspection, ReduceReconcileReport


class ExtractionPipelineInspectionTest(unittest.TestCase):
    def test_extraction_pipeline_inspection_summarizes_stages_and_markdown(self) -> None:
        created_at = datetime.now(timezone.utc)
        inspection = build_extraction_pipeline_inspection(
            {
                "id": "job-1",
                "document_id": "doc-1",
                "version_id": "ver-1",
                "status": "degraded",
                "current_stage": "verify",
                "source_type": "diagram_pdf",
                "document_type": "workflow_diagram",
                "risk_level": "high",
                "created_at": created_at,
                "updated_at": created_at,
                "map_units": [
                    {
                        "unit_id": "unit_element_1",
                        "unit_index": 0,
                        "unit_type": "workflow_step",
                        "title": "Start",
                        "status": "completed",
                        "attempt_count": 1,
                        "last_error": "",
                        "evidence_hash": "abc123",
                    }
                ],
                "compilation_plans": [
                    {
                        "id": "plan-1",
                        "job_id": "job-1",
                        "plan_version": "document_compilation_plan_v1",
                        "status": "pending_review",
                        "operation_count": 3,
                        "human_approval_required": True,
                        "payload": {"document_type": "workflow_diagram"},
                        "source_coverage": {"source_element_count": 5},
                        "review_gates": {"approval_required_before_publish": True},
                        "created_at": created_at,
                        "updated_at": created_at,
                    }
                ],
                "reduce_items": [
                    {
                        "id": "reduce-1",
                        "job_id": "job-1",
                        "item_kind": "claim",
                        "item_key": "claim:workflow_step:start",
                        "title": "Start",
                        "status": "suggested",
                        "duplicate_count": 1,
                        "source_unit_ids": ["unit_element_1"],
                        "evidence_hashes": ["abc123"],
                        "payload": {"unit_type": "workflow_step"},
                        "created_at": created_at,
                        "updated_at": created_at,
                    }
                ],
                "outputs": [
                    {
                        "id": "out-1",
                        "job_id": "job-1",
                        "stage": "workflow_semantic_refine",
                        "artifact_type": "workflow_semantic_refinement",
                        "payload": {"warnings": ["uncertain_edges_created"], "summary": {"uncertain_edge_count": 2}},
                        "status": "completed",
                        "error": "",
                        "created_at": created_at,
                    },
                    {
                        "id": "out-map",
                        "job_id": "job-1",
                        "stage": "map",
                        "artifact_type": "map_unit_extracts",
                        "payload": {
                            "unit_count": 4,
                            "source_element_count": 5,
                            "mapped_source_element_count": 4,
                            "unmapped_source_element_count": 1,
                            "blocked_unit_count": 1,
                        },
                        "status": "completed",
                        "error": "",
                        "created_at": created_at,
                    },
                    {
                        "id": "out-2",
                        "job_id": "job-1",
                        "stage": "verify",
                        "artifact_type": "verification_report",
                        "payload": {"hard_blockers": ["missing_atomic_units"], "coverage_score": 15, "warnings": ["missing_related_sop"]},
                        "status": "failed",
                        "error": "",
                        "created_at": created_at,
                    },
                ],
            }
        )

        workflow_stage = next(stage for stage in inspection["stage_summary"] if stage["stage"] == "workflow_semantic_refine")
        verify_stage = next(stage for stage in inspection["stage_summary"] if stage["stage"] == "verify")

        self.assertEqual(workflow_stage["output_count"], 1)
        self.assertIn("workflow_semantic_refinement", workflow_stage["artifact_types"])
        self.assertEqual(verify_stage["statuses"], ["failed"])
        self.assertEqual(inspection["issue_summary"]["failed_output_count"], 1)
        self.assertEqual(inspection["issue_summary"]["map_unit_count"], 4)
        self.assertEqual(inspection["issue_summary"]["map_source_element_count"], 5)
        self.assertEqual(inspection["issue_summary"]["unmapped_source_element_count"], 1)
        self.assertEqual(inspection["issue_summary"]["map_blocked_unit_count"], 1)
        self.assertEqual(inspection["issue_summary"]["hard_blockers"], ["missing_atomic_units"])
        self.assertEqual(inspection["issue_summary"]["coverage_score"], 15)
        self.assertEqual(inspection["map_units"][0]["unit_id"], "unit_element_1")
        self.assertEqual(inspection["map_units"][0]["attempt_count"], 1)
        self.assertEqual(inspection["compilation_plans"][0]["plan_version"], "document_compilation_plan_v1")
        self.assertEqual(inspection["reduce_items"][0]["item_kind"], "claim")
        self.assertIn("workflow_semantic_refine", inspection["summary_markdown"])
        self.assertIn("Map units: 4", inspection["summary_markdown"])
        self.assertIn("missing_atomic_units", inspection["summary_markdown"])

        response_model = ExtractionPipelineInspection(**inspection)

        self.assertEqual(response_model.issue_summary.map_unit_count, 4)
        self.assertEqual(response_model.map_units[0].unit_id, "unit_element_1")
        self.assertEqual(response_model.compilation_plans[0].status, "pending_review")
        self.assertEqual(response_model.reduce_items[0].title, "Start")

    def test_reduce_reconcile_report_summarizes_duplicates_and_conflicts(self) -> None:
        created_at = datetime.now(timezone.utc)
        report = build_reduce_reconcile_report(
            {
                "id": "job-1",
                "document_id": "doc-1",
                "version_id": "ver-1",
                "status": "degraded",
                "current_stage": "verify",
                "reduce_items": [
                    {
                        "id": "reduce-1",
                        "job_id": "job-1",
                        "item_kind": "claim",
                        "item_key": "claim:policy_rule:refund",
                        "title": "Refund threshold",
                        "status": "suggested",
                        "score": 0.91,
                        "duplicate_count": 3,
                        "source_unit_ids": ["unit-1", "unit-2", "unit-3"],
                        "evidence_hashes": ["hash-1", "hash-2"],
                        "payload": {"unit_type": "policy_rule"},
                        "created_at": created_at,
                        "updated_at": created_at,
                    }
                ],
                "outputs": [
                    {
                        "id": "out-reconcile",
                        "job_id": "job-1",
                        "stage": "reduce",
                        "artifact_type": "reconcile_suggestions",
                        "payload": {
                            "duplicate_title": [{"document_id": "doc-2", "title": "Refund threshold", "score": 1.0}],
                            "related_sop": [{"document_id": "doc-3", "title": "Refund SOP", "score": 2}],
                            "possible_conflict": [{"document_id": "doc-4", "title": "Refund exception", "score": 2.4}],
                            "summary": {"duplicate_title_count": 1, "related_sop_count": 1, "possible_conflict_count": 1},
                        },
                        "status": "completed",
                        "error": "",
                        "created_at": created_at,
                    },
                    {
                        "id": "out-verify",
                        "job_id": "job-1",
                        "stage": "verify",
                        "artifact_type": "reduce_reconcile_verification",
                        "payload": {
                            "conflict_count": 1,
                            "conflicts": [{"type": "rounding_apply_conflict", "titles": ["A", "B"]}],
                        },
                        "status": "failed",
                        "error": "",
                        "created_at": created_at,
                    },
                ],
            }
        )

        self.assertEqual(report["summary"]["reduce_item_count"], 1)
        self.assertEqual(report["summary"]["duplicate_claim_count"], 1)
        self.assertEqual(report["summary"]["duplicate_title_count"], 1)
        self.assertEqual(report["summary"]["conflict_count"], 2)
        self.assertEqual(report["duplicate_claims"][0]["title"], "Refund threshold")
        self.assertEqual(report["duplicate_titles"][0]["title"], "Refund threshold")
        self.assertEqual(report["conflicts"][0]["type"], "possible_conflict")
        self.assertEqual(report["conflicts"][1]["type"], "rounding_apply_conflict")
        self.assertIn("Duplicate claims: 1", report["summary_markdown"])

        response_model = ReduceReconcileReport(**report)

        self.assertEqual(response_model.summary["conflict_count"], 2)
        self.assertEqual(response_model.duplicate_claims[0].duplicate_count, 3)
