from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import embedding_migration_worker


class EmbeddingMigrationWorkerTest(unittest.TestCase):
    def test_run_pending_embedding_migrations_batches_until_no_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        list_calls: list[tuple[tuple[str, ...], int]] = []

        def list_jobs(*, statuses: list[str], limit: int) -> list[dict[str, object]]:
            list_calls.append((tuple(statuses), limit))
            if len(list_calls) <= 2:
                return [
                    {
                        "id": "job-1",
                        "source_spec_id": "local_hash:local_hash:1536",
                        "target_spec_id": "openrouter:openai/text-embedding-3-small:1536",
                        "status": "pending" if len(list_calls) == 1 else "in_progress",
                        "total_items": 5,
                        "processed_items": 0,
                        "error": "",
                        "created_at": now,
                        "updated_at": now,
                        "completed_at": None,
                    }
                ]
            return []

        run_results = [
            {
                "id": "job-1",
                "status": "in_progress",
                "total_items": 5,
                "processed_items": 3,
                "metadata": {"processed_batch": 3, "remaining_items": 2},
            },
            {
                "id": "job-1",
                "status": "completed",
                "total_items": 5,
                "processed_items": 5,
                "metadata": {"processed_batch": 2, "remaining_items": 0},
            },
        ]

        with (
            patch(
                "app.embedding_migration_worker.repository.list_embedding_migration_jobs",
                side_effect=list_jobs,
            ) as list_pending,
            patch(
                "app.embedding_migration_worker.repository.run_embedding_migration_job",
                side_effect=run_results,
            ) as run_job,
        ):
            summary = embedding_migration_worker.run_pending_embedding_migrations(
                batch_size=3,
                max_batches=5,
            )

        self.assertEqual(summary["stopped_reason"], "no_jobs")
        self.assertEqual(summary["job_count"], 1)
        self.assertEqual(summary["batch_count"], 2)
        self.assertEqual(summary["processed_items"], 5)
        self.assertEqual(summary["remaining_items"], 0)
        self.assertEqual(summary["jobs"][0]["id"], "job-1")
        self.assertEqual(summary["jobs"][0]["status"], "completed")
        list_pending.assert_called()
        run_job.assert_any_call("job-1", batch_size=3)
        self.assertEqual(list_calls[0], (("pending", "in_progress"), 1))

    def test_run_pending_embedding_migrations_stops_when_job_makes_no_progress(self) -> None:
        with (
            patch(
                "app.embedding_migration_worker.repository.list_embedding_migration_jobs",
                return_value=[{"id": "job-1", "status": "in_progress"}],
            ),
            patch(
                "app.embedding_migration_worker.repository.run_embedding_migration_job",
                return_value={
                    "id": "job-1",
                    "status": "in_progress",
                    "total_items": 5,
                    "processed_items": 2,
                    "metadata": {"processed_batch": 0, "remaining_items": 3},
                },
            ) as run_job,
        ):
            summary = embedding_migration_worker.run_pending_embedding_migrations(
                batch_size=10,
                max_batches=5,
            )

        self.assertEqual(summary["stopped_reason"], "no_progress")
        self.assertEqual(summary["batch_count"], 1)
        self.assertEqual(summary["remaining_items"], 3)
        run_job.assert_called_once_with("job-1", batch_size=10)


if __name__ == "__main__":
    unittest.main()
