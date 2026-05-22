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
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=12), \
            patch("app.retrieval.embed_text", side_effect=EmbeddingProviderError("down")):
            response = retrieve(RetrievalRequest(query="refund pending", mode="hybrid", limit=3))

        vector_search.assert_not_called()
        self.assertIn("embedding_unavailable", response.warnings)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].rank_source, ["lexical"])

    def test_hybrid_degrades_to_lexical_when_vector_search_fails(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]), \
            patch("app.retrieval.repository.vector_search", side_effect=TypeError("bad vector dimension")), \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=12), \
            patch("app.retrieval.embed_text", return_value=[0.1, 0.2]):
            response = retrieve(RetrievalRequest(query="refund pending", mode="hybrid", limit=3))

        self.assertIn("vector_search_failed:TypeError", response.warnings)
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

    def test_vector_only_returns_warning_when_vector_search_fails(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.vector_search", side_effect=TypeError("bad vector dimension")), \
            patch("app.retrieval.repository.log_retrieval", return_value=9), \
            patch("app.retrieval.embed_text", return_value=[0.1, 0.2]):
            response = retrieve(RetrievalRequest(query="refund pending", mode="vector", limit=3))

        self.assertEqual(response.results, [])
        self.assertIn("vector_search_failed:TypeError", response.warnings)
        self.assertIn("no_reliable_source", response.warnings)

    def test_debug_retrieval_persists_candidate_trace(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]), \
            patch("app.retrieval.repository.vector_search", return_value=[]), \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=12) as log_retrieval:
            response = retrieve(RetrievalRequest(query="refund pending", mode="lexical", ranking_mode="ai_chat", limit=3, debug=True))

        trace = log_retrieval.call_args.kwargs.get("trace")
        self.assertIsInstance(trace, dict)
        self.assertEqual(trace["ranking_debug"]["keyword_candidate_count"], 1)
        self.assertEqual(trace["ranking_debug"]["final_selected_context_ids"], ["chunk-1"])
        self.assertEqual(trace["selected_context"][0]["chunk_id"], "chunk-1")
        self.assertEqual(response.ranking_debug["final_selected_context_ids"], ["chunk-1"])

    def test_ai_chat_applies_confident_query_understanding_filters_to_candidate_generation(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]) as lexical_search, \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=12), \
            patch("app.ranking.settings.openrouter_api_key", ""):
            retrieve(
                RetrievalRequest(
                    query="CS có được nói cho khách tài xế bị khóa vì vi phạm 3 lần không",
                    mode="lexical",
                    ranking_mode="ai_chat",
                    limit=3,
                    debug=True,
                )
            )

        applied_filters = lexical_search.call_args.args[1]
        self.assertEqual(applied_filters.scope, ["sanction_policy"])
        self.assertEqual(applied_filters.visibility, ["customer_facing"])


if __name__ == "__main__":
    unittest.main()
