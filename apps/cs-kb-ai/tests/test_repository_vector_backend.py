import unittest
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


if __name__ == "__main__":
    unittest.main()
