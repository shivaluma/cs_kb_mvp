from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
