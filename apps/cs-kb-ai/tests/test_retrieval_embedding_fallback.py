import unittest
from unittest.mock import patch

from app.embedding import EmbeddingProviderError
from app.retrieval import retrieve
from app.schemas import RetrievalRequest


def retrieval_row(
    chunk_id: str = "chunk-1",
    *,
    heading: str = "Refund pending",
    content: str = "Handle refund pending requests.",
    score: float = 1.2,
    source_ref_quality: str = "structured",
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "version_id": "version-1",
        "title": "Refund SOP",
        "source_filename": "refund.md",
        "version_number": 1,
        "chunk_index": 0,
        "section": "policy_rule",
        "heading": heading,
        "content": content,
        "metadata": {
            "unit_type": "policy_rule",
            "review_status": "approved",
            "extraction_status": "structured",
            "source_ref_quality": source_ref_quality,
        },
        "score": score,
    }


def compiled_page_row() -> dict[str, object]:
    return {
        "chunk_id": "page-1",
        "document_id": "doc-1",
        "version_id": "version-1",
        "title": "Refund SOP",
        "source_filename": "refund.md",
        "version_number": 1,
        "chunk_index": -1,
        "section": "document_overview",
        "heading": "Refund SOP",
        "content": "Full refund handling instructions compiled from approved units.",
        "metadata": {
            "unit_type": "compiled_document_overview",
            "chunk_type": "compiled_document_overview",
            "retrieval_scope": "document",
            "review_status": "approved",
            "extraction_status": "structured",
        },
        "score": 0.72,
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

    def test_vector_only_falls_back_to_lexical_when_embedding_is_unavailable(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]), \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=9), \
            patch("app.retrieval.embed_text", side_effect=EmbeddingProviderError("down")):
            response = retrieve(RetrievalRequest(query="refund pending", mode="vector", limit=3))

        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].rank_source, ["lexical"])
        self.assertIn("embedding_unavailable", response.warnings)
        self.assertIn("vector_mode_lexical_fallback", response.warnings)
        self.assertNotIn("no_reliable_source", response.warnings)

    def test_vector_only_falls_back_to_lexical_when_vector_search_fails(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.lexical_search", return_value=[retrieval_row()]), \
            patch("app.retrieval.repository.vector_search", side_effect=TypeError("bad vector dimension")), \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=9), \
            patch("app.retrieval.embed_text", return_value=[0.1, 0.2]):
            response = retrieve(RetrievalRequest(query="refund pending", mode="vector", limit=3))

        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].rank_source, ["lexical"])
        self.assertIn("vector_search_failed:TypeError", response.warnings)
        self.assertIn("vector_mode_lexical_fallback", response.warnings)
        self.assertNotIn("no_reliable_source", response.warnings)

    def test_vector_fallback_backfills_postgres_when_meili_misses_structured_row(self) -> None:
        meili_row = retrieval_row(
            "broad",
            heading="TX bị khóa bởi SI, yêu cầu gọi số khác",
            content="Trường hợp tài xế yêu cầu gọi qua số điện thoại khác.",
            score=0.5,
        )
        meili_row["from_meilisearch"] = True
        meili_row["rank_source"] = ["meilisearch"]
        postgres_row = retrieval_row(
            "taxi-row",
            heading="SĐT hãng Taxi Thành Lợi",
            content="Tên Hãng: Thành Lợi; SĐT: 0243551551",
            score=0.2,
        )
        with patch("app.retrieval.settings.meili_host", "http://meili.local"), \
            patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.meili_ai_chunk_search", return_value=[meili_row]), \
            patch("app.retrieval.repository.lexical_search", return_value=[postgres_row]), \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=9), \
            patch("app.retrieval.embed_text", side_effect=EmbeddingProviderError("down")):
            response = retrieve(RetrievalRequest(query="số điện thoại taxi thành lợi", mode="vector", limit=3, debug=True))

        self.assertEqual(response.results[0].chunk_id, "taxi-row")
        self.assertEqual(response.results[0].rank_source, ["lexical"])
        self.assertIn("embedding_unavailable", response.warnings)
        self.assertIn("meili_keyword_postgres_backfill", response.warnings)
        self.assertIn("vector_mode_lexical_fallback", response.warnings)

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

    def test_vector_retrieval_can_include_compiled_page_context(self) -> None:
        with patch("app.retrieval.repository.active_synonym_groups", return_value=[]), \
            patch("app.retrieval.repository.vector_search", return_value=[]), \
            patch("app.retrieval.repository.compiled_page_vector_search", return_value=[compiled_page_row()]) as compiled_search, \
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[]), \
            patch("app.retrieval.repository.display_context_rows_for_results", return_value={}), \
            patch("app.retrieval.repository.log_retrieval", return_value=12), \
            patch("app.retrieval.embed_text", return_value=[0.1, 0.2]):
            response = retrieve(
                RetrievalRequest(query="refund overview", mode="vector", include_compiled_pages=True, limit=3, debug=True)
            )

        compiled_search.assert_called_once()
        self.assertEqual(response.results[0].chunk_id, "page-1")
        self.assertEqual(response.results[0].metadata["unit_type"], "compiled_document_overview")
        self.assertEqual(response.results[0].rank_source, ["vector"])
        self.assertEqual(response.ranking_debug["compiled_page_candidate_count"], 1)

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
