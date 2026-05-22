import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import UploadFile

from app.main import upload_document


def published_version() -> dict[str, object]:
    return {
        "document_id": "doc-1",
        "version_id": "ver-1",
        "external_id": "ext-1",
        "title": "Driver sanction SOP",
        "version_number": 1,
        "status": "published",
        "publish_state": "published_indexing_pending",
        "chunk_count": 1,
        "checksum": "abc",
        "document_type": "text_sop",
        "review_status": "approved",
        "extraction_confidence": 0.98,
        "metadata": {},
        "indexed_at": None,
        "indexing_error": "",
        "published_ready_at": None,
    }


class UploadDocumentQdrantIndexingTest(unittest.IsolatedAsyncioTestCase):
    async def test_published_upload_includes_vector_indexing_status(self) -> None:
        file = UploadFile(file=BytesIO(b"# SOP\nDo not disclose sanction thresholds."), filename="sop.md")
        with patch(
            "app.main.prepare_document_version",
            return_value=(
                "raw text",
                "checksum-1",
                [{"content": "Do not disclose sanction thresholds."}],
                [],
                {
                    "document_type": "text_sop",
                    "review_status": "reviewed",
                    "extraction_confidence": 0.98,
                },
            ),
        ), patch("app.main.repository.create_document_version", return_value=published_version()), \
            patch(
                "app.main.repository.sync_qdrant_version",
                return_value={
                    "vector_backend": "qdrant",
                    "vector_index_verified": False,
                    "qdrant_indexed_count": 0,
                    "vector_indexing_error": "qdrant down",
                },
            ) as sync_qdrant:
            response = await upload_document(
                file=file,
                status="published",
                metadata="{}",
                external_id="",
                title="",
                created_by="system",
                change_summary="",
            )

        sync_qdrant.assert_called_once_with("ver-1")
        self.assertEqual(response.vector_backend, "qdrant")
        self.assertFalse(response.vector_index_verified)
        self.assertEqual(response.vector_indexing_error, "qdrant down")


if __name__ == "__main__":
    unittest.main()
