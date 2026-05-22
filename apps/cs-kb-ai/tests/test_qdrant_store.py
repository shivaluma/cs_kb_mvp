import unittest

from app import qdrant_store
from app.schemas import RetrievalFilters


class QdrantStoreTest(unittest.TestCase):
    def test_filter_requires_published_current_chunks_by_default(self) -> None:
        query_filter = qdrant_store.build_filter(RetrievalFilters())

        self.assertEqual(
            query_filter["must"],
            [
                {"key": "document_status", "match": {"value": "active"}},
                {"key": "status", "match": {"any": ["published"]}},
                {"key": "is_current_version", "match": {"value": True}},
                {"key": "publish_state", "match": {"value": "published_ready"}},
                {"key": "review_status", "match": {"value": "approved"}},
                {"key": "extraction_status", "match": {"any": ["structured", "manually_curated"]}},
                {"key": "publish_blocked", "match": {"value": False}},
            ],
        )

    def test_filter_maps_metadata_lists_to_payload_conditions(self) -> None:
        query_filter = qdrant_store.build_filter(
            RetrievalFilters(
                audience=["driver"],
                visibility=["customer_facing"],
                scope=["sanction_policy"],
                collections=["cs-core"],
                document_ids=["doc-1"],
            )
        )

        self.assertIn({"key": "audience", "match": {"any": ["driver"]}}, query_filter["must"])
        self.assertIn({"key": "visibility", "match": {"any": ["customer_facing"]}}, query_filter["must"])
        self.assertIn({"key": "scope", "match": {"any": ["sanction_policy"]}}, query_filter["must"])
        self.assertIn({"key": "collections", "match": {"any": ["cs-core"]}}, query_filter["must"])
        self.assertIn({"key": "document_id", "match": {"any": ["doc-1"]}}, query_filter["must"])

    def test_payload_from_row_contains_authority_and_source_metadata(self) -> None:
        payload = qdrant_store.payload_from_row(
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "version_id": "ver-1",
                "title": "Driver sanction SOP",
                "source_filename": "sop.md",
                "version_number": 3,
                "status": "published",
                "publish_state": "published_ready",
                "review_status": "approved",
                "document_status": "active",
                "is_current_version": True,
                "chunk_index": 2,
                "section": "Compliance",
                "heading": "Do not disclose thresholds",
                "metadata": {
                    "visibility": "customer_facing",
                    "scope": "sanction_policy",
                    "authority_level": "policy",
                    "policy_type": "compliance_rule",
                    "risk_level": "high",
                    "source_ref_quality": "exact",
                    "audience": ["driver"],
                    "collection_slug": "cs-core",
                    "tags": ["sanction"],
                    "case_reasons": ["driver_locked"],
                    "vertical": "transport",
                    "category": "Trust",
                    "unit_type": "policy_rule",
                    "publish_blocked": False,
                    "extraction_status": "structured",
                },
            }
        )

        self.assertEqual(payload["chunk_id"], "chunk-1")
        self.assertEqual(payload["visibility"], "customer_facing")
        self.assertEqual(payload["scope"], "sanction_policy")
        self.assertEqual(payload["authority_level"], "policy")
        self.assertEqual(payload["collections"], ["cs-core"])
        self.assertEqual(payload["source_ref_quality"], "exact")

    def test_parse_vector_text_accepts_pgvector_text(self) -> None:
        self.assertEqual(qdrant_store.parse_vector("[0.1, -0.2, 3]"), [0.1, -0.2, 3.0])

    def test_payload_supports_collection_arrays(self) -> None:
        payload = qdrant_store.payload_from_row(
            {
                "chunk_id": "chunk-1",
                "metadata": {
                    "collections": ["cs-core", "trust"],
                    "collection_slug": "legacy",
                },
            }
        )

        self.assertEqual(payload["collections"], ["cs-core", "trust", "legacy"])


if __name__ == "__main__":
    unittest.main()
