from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.main import update_extraction_compilation_plan
from app.schemas import ExtractionCompilationPlanStatusUpdateRequest


class ExtractionCompilationPlanEndpointTest(unittest.TestCase):
    def test_update_extraction_compilation_plan_delegates_status_change(self) -> None:
        now = datetime.now(timezone.utc)
        with patch(
            "app.main.repository.update_extraction_compilation_plan_status",
            return_value={
                "id": "plan-1",
                "job_id": "job-1",
                "plan_version": "document_compilation_plan_v1",
                "status": "approved",
                "payload": {"operation_count": 2},
                "operation_count": 2,
                "human_approval_required": True,
                "source_coverage": {"source_element_count": 3},
                "review_gates": {"approval_required_before_publish": True},
                "last_error": "",
                "created_at": now,
                "updated_at": now,
                "approved_at": now,
                "approved_by": "cs-lead",
                "rejected_at": None,
                "rejection_reason": "",
            },
        ) as update_status:
            response = update_extraction_compilation_plan(
                "plan-1",
                ExtractionCompilationPlanStatusUpdateRequest(status="approved", actor="cs-lead"),
            )

        update_status.assert_called_once_with(
            plan_id="plan-1",
            status="approved",
            actor="cs-lead",
            rejection_reason="",
            error="",
        )
        self.assertEqual(response.status, "approved")
        self.assertEqual(response.approved_by, "cs-lead")


if __name__ == "__main__":
    unittest.main()
