import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app import repository
from app.schemas import RetrievalFilters


class RepositoryVectorBackendTest(unittest.TestCase):
    def test_dual_backend_uses_qdrant_hits_before_pgvector(self) -> None:
        hydrated = [{"chunk_id": "chunk-1", "score": 0.91}]
        with patch("app.repository.settings.vector_backend", "dual"), \
            patch("app.repository.qdrant_store.qdrant_configured", return_value=True), \
            patch("app.repository.qdrant_store.search", return_value=[{"chunk_id": "chunk-1", "score": 0.91}]) as qdrant_search, \
            patch("app.repository.hydrate_vector_hits", return_value=hydrated) as hydrate, \
            patch("app.repository.pgvector_search") as pgvector_search:
            rows = repository.vector_search([0.1, 0.2], RetrievalFilters(), 5)

        self.assertEqual(rows, hydrated)
        qdrant_search.assert_called_once()
        hydrate.assert_called_once()
        pgvector_search.assert_not_called()

    def test_dual_backend_falls_back_to_pgvector_when_qdrant_fails(self) -> None:
        fallback = [{"chunk_id": "chunk-pg", "score": 0.75}]
        with patch("app.repository.settings.vector_backend", "dual"), \
            patch("app.repository.qdrant_store.qdrant_configured", return_value=True), \
            patch("app.repository.qdrant_store.search", side_effect=RuntimeError("qdrant down")), \
            patch("app.repository.pgvector_search", return_value=fallback) as pgvector_search:
            rows = repository.vector_search([0.1, 0.2], RetrievalFilters(), 5)

        self.assertEqual(rows, fallback)
        pgvector_search.assert_called_once()

    def test_qdrant_only_does_not_fall_back_to_pgvector(self) -> None:
        with patch("app.repository.settings.vector_backend", "qdrant"), \
            patch("app.repository.qdrant_store.qdrant_configured", return_value=True), \
            patch("app.repository.qdrant_store.search", side_effect=RuntimeError("qdrant down")), \
            patch("app.repository.pgvector_search") as pgvector_search:
            with self.assertRaises(RuntimeError):
                repository.vector_search([0.1, 0.2], RetrievalFilters(), 5)

        pgvector_search.assert_not_called()

    def test_sync_qdrant_version_returns_verified_false_when_sync_fails(self) -> None:
        with patch("app.repository.qdrant_store.qdrant_configured", return_value=True), \
            patch("app.repository.qdrant_index_rows_for_version", return_value=[{"chunk_id": "chunk-1"}]), \
            patch("app.repository.qdrant_store.upsert_points", side_effect=RuntimeError("qdrant down")):
            result = repository.sync_qdrant_version("ver-1")

        self.assertFalse(result["vector_index_verified"])
        self.assertEqual(result["vector_backend"], "qdrant")
        self.assertIn("qdrant down", result["vector_indexing_error"])

    def test_qdrant_index_rows_apply_production_chunk_filters(self) -> None:
        fake = RecordingConnection()

        @contextmanager
        def fake_connection():
            yield fake

        with patch("app.repository.connection", fake_connection):
            rows = repository.qdrant_index_rows_for_version("ver-1")

        self.assertEqual(rows, [])
        self.assertIn("COALESCE(c.metadata->>'review_status', '') = 'approved'", fake.query)
        self.assertIn("COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)", fake.query)
        self.assertIn("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'", fake.query)
        self.assertIn("COALESCE(c.metadata->>'source_evidence_only', 'false') <> 'true'", fake.query)
        self.assertIn("COALESCE(c.metadata->>'unit_type', '') NOT IN ('source_evidence_section', 'visual_source_block')", fake.query)
        self.assertIn(["structured", "manually_curated"], fake.params)

    def test_qdrant_post_filter_rejects_workflow_chunk_without_bbox(self) -> None:
        self.assertFalse(
            repository.production_indexable_chunk_row(
                {
                    "section": "decision_branch",
                    "content": "Decision 8: Nếu No, chuyển đến 8.2: thông báo theo source.",
                    "metadata": {
                        "unit_type": "decision_branch",
                        "review_status": "approved",
                        "extraction_status": "structured",
                        "source_refs": [{"page": 1}],
                        "from_step_code": "8",
                        "to_step_code": "8.2",
                        "condition": "no",
                    },
                }
            )
        )


class RecordingConnection:
    def __init__(self) -> None:
        self.query = ""
        self.params: tuple[object, ...] = ()
        self.row_factory = None

    def execute(self, query: str, params: tuple[object, ...]) -> "RecordingConnection":
        self.query = query
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []


if __name__ == "__main__":
    unittest.main()
