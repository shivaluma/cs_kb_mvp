from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.main import create_embedding_migration_plan, run_embedding_migration_job
from app.schemas import EmbeddingMigrationPlanRequest, EmbeddingMigrationRunRequest


class EmbeddingMigrationEndpointTest(unittest.TestCase):
    def test_create_embedding_migration_plan_delegates_to_repository(self) -> None:
        now = datetime.now(timezone.utc)
        with patch(
            "app.main.repository.create_embedding_migration_plan",
            return_value={
                "id": "job-1",
                "source_spec_id": "local_hash:local_hash:1536",
                "target_spec_id": "openrouter:openai/text-embedding-3-small:1536",
                "status": "pending",
                "total_items": 12,
                "processed_items": 0,
                "error": "",
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "metadata": {"chunk_count": 10, "compiled_page_count": 2},
            },
        ) as create_plan:
            response = create_embedding_migration_plan(
                EmbeddingMigrationPlanRequest(
                    provider="openrouter",
                    model="openai/text-embedding-3-small",
                    dimensions=1536,
                    source_spec_id="local_hash:local_hash:1536",
                )
            )

        create_plan.assert_called_once_with(
            provider="openrouter",
            model="openai/text-embedding-3-small",
            dimensions=1536,
            source_spec_id="local_hash:local_hash:1536",
        )
        self.assertEqual(response.status, "pending")
        self.assertEqual(response.total_items, 12)
        self.assertEqual(response.metadata["compiled_page_count"], 2)

    def test_run_embedding_migration_job_delegates_batch_execution(self) -> None:
        now = datetime.now(timezone.utc)
        with patch(
            "app.main.repository.run_embedding_migration_job",
            return_value={
                "id": "job-1",
                "source_spec_id": "local_hash:local_hash:1536",
                "target_spec_id": "openrouter:openai/text-embedding-3-small:1536",
                "status": "in_progress",
                "total_items": 12,
                "processed_items": 5,
                "error": "",
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "metadata": {"processed_batch": 5, "remaining_items": 7},
            },
        ) as run_job:
            response = run_embedding_migration_job("job-1", EmbeddingMigrationRunRequest(batch_size=5))

        run_job.assert_called_once_with("job-1", batch_size=5)
        self.assertEqual(response.status, "in_progress")
        self.assertEqual(response.processed_items, 5)
        self.assertEqual(response.metadata["remaining_items"], 7)


if __name__ == "__main__":
    unittest.main()
