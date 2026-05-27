from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.main import update_extraction_map_unit
from app.schemas import ExtractionMapUnitStatusUpdateRequest


class ExtractionMapUnitEndpointTest(unittest.TestCase):
    def test_update_extraction_map_unit_delegates_status_change(self) -> None:
        now = datetime.now(timezone.utc)
        with patch(
            "app.main.repository.update_extraction_map_unit_status",
            return_value={
                "id": "row-1",
                "job_id": "job-1",
                "unit_id": "unit_element_1",
                "unit_index": 0,
                "unit_type": "policy_rule",
                "title": "Refund rule",
                "status": "in_progress",
                "confidence": 0.87,
                "evidence_hash": "hash-1",
                "source_element_ids": ["element_1"],
                "missing_source_element_ids": [],
                "source_refs": [{"source_type": "text", "line_start": 1}],
                "source_ref_quality": "line",
                "warnings": ["retry"],
                "attempt_count": 2,
                "last_error": "",
                "started_at": now,
                "completed_at": None,
                "updated_at": now,
                "created_at": now,
            },
        ) as update_status:
            response = update_extraction_map_unit(
                "job-1",
                "unit_element_1",
                ExtractionMapUnitStatusUpdateRequest(status="in_progress", warnings=["retry"]),
            )

        update_status.assert_called_once_with(
            job_id="job-1",
            unit_id="unit_element_1",
            status="in_progress",
            error="",
            warnings=["retry"],
        )
        self.assertEqual(response.status, "in_progress")
        self.assertEqual(response.attempt_count, 2)


if __name__ == "__main__":
    unittest.main()
