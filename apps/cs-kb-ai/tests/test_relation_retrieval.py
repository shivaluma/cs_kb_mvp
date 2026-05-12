from __future__ import annotations

import unittest
from unittest.mock import patch

from app import retrieval
from app.schemas import RetrievalRequest


class RelationRetrievalTest(unittest.TestCase):
    def test_approved_relation_rows_are_appended_after_reliable_sources(self) -> None:
        base_row = {
            "chunk_id": "source-chunk",
            "document_id": "source-doc",
            "version_id": "source-version",
            "title": "Quy định chuyển Tech",
            "source_filename": "source.md",
            "version_number": 1,
            "chunk_index": 0,
            "section": "policy_rule",
            "heading": "Chuyển Tech",
            "content": "Khi chuyển Tech cần dùng tasklist.",
            "metadata": {"unit_type": "policy_rule", "review_status": "approved", "extraction_status": "structured"},
            "score": 0.8,
        }
        relation_row = {
            "chunk_id": "target-chunk",
            "document_id": "target-doc",
            "version_id": "target-version",
            "title": "Quy định sử dụng tasklist",
            "source_filename": "target.md",
            "version_number": 3,
            "chunk_index": 0,
            "section": "full_sop",
            "heading": "Tasklist",
            "content": "Tasklist phải có mô tả và owner.",
            "metadata": {"unit_type": "full_sop", "relation_type": "requires"},
            "score": 0.005,
            "lexical_score": 0.0,
            "vector_score": 0.0,
            "rank_source": ["approved_relation"],
            "best_rank": 999,
        }

        with (
            patch("app.retrieval.repository.active_synonym_groups", return_value=[]),
            patch("app.retrieval.repository.lexical_search", return_value=[base_row]),
            patch("app.retrieval.repository.vector_search", return_value=[]),
            patch("app.retrieval.repository.approved_relation_target_rows", return_value=[relation_row]) as relation_rows,
            patch("app.retrieval.repository.log_retrieval", return_value=2),
        ):
            response = retrieval.retrieve(RetrievalRequest(query="chuyen tech tasklist", mode="lexical", limit=3))

        relation_rows.assert_called_once_with(["source-doc"], ["source-chunk"], 2)
        self.assertEqual([result.chunk_id for result in response.results], ["source-chunk", "target-chunk"])
        self.assertEqual(response.results[1].rank_source, ["approved_relation"])


if __name__ == "__main__":
    unittest.main()
