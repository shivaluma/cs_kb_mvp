from __future__ import annotations

import json
import unittest

from app import repository


class RepositoryEmbeddingMigrationTest(unittest.TestCase):
    def test_list_embedding_migration_jobs_tx_filters_statuses_and_limits(self) -> None:
        class FakeResult:
            def fetchall(self) -> list[dict[str, object]]:
                return [
                    {
                        "id": "job-1",
                        "source_spec_id": "local_hash:local_hash:1536",
                        "target_spec_id": "openrouter:openai/text-embedding-3-small:1536",
                        "status": "pending",
                        "total_items": 10,
                        "processed_items": 0,
                        "error": "",
                    }
                ]

        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def execute(self, sql: str, params: tuple[object, ...]) -> FakeResult:
                self.sql = sql
                self.params = params
                return FakeResult()

        conn = FakeConnection()

        rows = repository.list_embedding_migration_jobs_tx(
            conn,
            statuses=["pending", "in_progress", ""],
            limit=500,
        )

        self.assertEqual(rows[0]["id"], "job-1")
        self.assertIn("j.status = ANY", conn.sql)
        self.assertIn("ORDER BY j.created_at ASC", conn.sql)
        self.assertEqual(conn.params, (["pending", "in_progress"], 100))

    def test_update_embedding_migration_items_updates_chunks_and_compiled_pages(self) -> None:
        class RecordingConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.calls.append((sql, params))

        conn = RecordingConnection()
        spec = {
            "spec_id": "openrouter:openai/text-embedding-3-small:1536",
            "provider": "openrouter",
            "model": "openai/text-embedding-3-small",
            "dimensions": 1536,
        }

        repository.update_embedding_migration_items_tx(
            conn,
            [
                {"item_kind": "chunk", "item_id": "chunk-1"},
                {"item_kind": "compiled_page", "item_id": "page-1"},
            ],
            [[0.1, 0.2], [0.3, 0.4]],
            spec,
            job_id="job-1",
        )

        sql_text = "\n".join(sql for sql, _params in conn.calls)
        self.assertIn("UPDATE ai_chunks", sql_text)
        self.assertIn("UPDATE ai_compiled_pages", sql_text)
        metadata_payloads = [json.loads(str(params[1])) for _sql, params in conn.calls]
        self.assertEqual(metadata_payloads[0]["embedding_spec_id"], "openrouter:openai/text-embedding-3-small:1536")
        self.assertEqual(metadata_payloads[0]["embedding_provider"], "openrouter")
        self.assertEqual(metadata_payloads[0]["embedding_migration_job_id"], "job-1")
        self.assertEqual(metadata_payloads[1]["embedding_model"], "openai/text-embedding-3-small")


if __name__ == "__main__":
    unittest.main()
