from __future__ import annotations

from app.main import build_extraction_pipeline_inspection


def test_extraction_pipeline_inspection_summarizes_stages_and_markdown() -> None:
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
            "created_at": None,
            "updated_at": None,
            "outputs": [
                {
                    "id": "out-1",
                    "job_id": "job-1",
                    "stage": "workflow_semantic_refine",
                    "artifact_type": "workflow_semantic_refinement",
                    "payload": {"warnings": ["uncertain_edges_created"], "summary": {"uncertain_edge_count": 2}},
                    "status": "completed",
                    "error": "",
                    "created_at": None,
                },
                {
                    "id": "out-2",
                    "job_id": "job-1",
                    "stage": "verify",
                    "artifact_type": "verification_report",
                    "payload": {"hard_blockers": ["missing_atomic_units"], "coverage_score": 15, "warnings": ["missing_related_sop"]},
                    "status": "failed",
                    "error": "",
                    "created_at": None,
                },
            ],
        }
    )

    workflow_stage = next(stage for stage in inspection["stage_summary"] if stage["stage"] == "workflow_semantic_refine")
    verify_stage = next(stage for stage in inspection["stage_summary"] if stage["stage"] == "verify")

    assert workflow_stage["output_count"] == 1
    assert "workflow_semantic_refinement" in workflow_stage["artifact_types"]
    assert verify_stage["statuses"] == ["failed"]
    assert inspection["issue_summary"]["failed_output_count"] == 1
    assert inspection["issue_summary"]["hard_blockers"] == ["missing_atomic_units"]
    assert inspection["issue_summary"]["coverage_score"] == 15
    assert "workflow_semantic_refine" in inspection["summary_markdown"]
    assert "missing_atomic_units" in inspection["summary_markdown"]
