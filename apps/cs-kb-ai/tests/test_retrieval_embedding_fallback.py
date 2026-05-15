import unittest
from unittest.mock import patch

from app.embedding import EmbeddingProviderError
from app.retrieval import retrieve
from app.schemas import RetrievalRequest


def retrieval_row(chunk_id: str = "chunk-1") -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "version_id": "version-1",
        "title": "Refund SOP",
        "source_filename": "refund.md",
        "version_number": 1,
        "chunk_index": 0,
        "section": "policy_rule",
        "heading": "Refund pending",
        "content": "Handle refund pending requests.",
        "metadata": {
            "unit_type": "policy_rule",
            "review_status": "approved",
            "extraction_status": "structured",
        },
        "score": 1.2,
    }


class RetrievalEmbeddingFallbackTest(unittest.TestCase):
    def test_hybrid_degrades_to_lexical_when_embedding_is_unavailable(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]), \
            patch("app.retrieval.repository.vector_search") as vector_search, \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.log_retrieval", return_value=12), \
            patch("app.retrieval.embed_text", side_effect=EmbeddingProviderError("down")):
            response = retrieve(RetrievalRequest(query="refund pending", mode="hybrid", limit=3))

        vector_search.assert_not_called()
        self.assertIn("embedding_unavailable", response.warnings)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].rank_source, ["lexical"])

    def test_vector_only_returns_warning_when_embedding_is_unavailable(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.log_retrieval", return_value=9), \
            patch("app.retrieval.embed_text", side_effect=EmbeddingProviderError("down")):
            response = retrieve(RetrievalRequest(query="refund pending", mode="vector", limit=3))

        self.assertEqual(response.results, [])
        self.assertIn("embedding_unavailable", response.warnings)
        self.assertIn("no_reliable_source", response.warnings)


if __name__ == "__main__":
    unittest.main()
