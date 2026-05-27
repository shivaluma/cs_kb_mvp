from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.main import get_version_reduce_reconcile_report


class ReduceReconcileReportEndpointTest(unittest.TestCase):
    def test_get_version_reduce_reconcile_report_uses_latest_pipeline_job(self) -> None:
        now = datetime.now(timezone.utc)
        with patch(
            "app.main.repository.list_extraction_pipeline",
            return_value=[
                {
                    "id": "job-1",
                    "document_id": "doc-1",
                    "version_id": "ver-1",
                    "status": "degraded",
                    "created_at": now,
                    "updated_at": now,
                    "reduce_items": [
                        {
                            "id": "reduce-1",
                            "job_id": "job-1",
                            "item_kind": "claim",
                            "item_key": "claim:policy_rule:refund",
                            "title": "Refund threshold",
                            "status": "suggested",
                            "duplicate_count": 2,
                            "source_unit_ids": ["unit-1", "unit-2"],
                            "evidence_hashes": ["hash-1"],
                            "payload": {"unit_type": "policy_rule"},
                            "created_at": now,
                            "updated_at": now,
                        }
                    ],
                    "outputs": [],
                }
            ],
        ) as list_pipeline:
            response = get_version_reduce_reconcile_report("ver-1")

        list_pipeline.assert_called_once_with("ver-1")
        self.assertEqual(response.summary["duplicate_claim_count"], 1)
        self.assertEqual(response.duplicate_claims[0].title, "Refund threshold")


if __name__ == "__main__":
    unittest.main()
