import unittest
from unittest.mock import patch

from app import embedding
from app.embedding import EmbeddingProviderError


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeClient:
    def __init__(self, body: dict) -> None:
        self.body = body
        self.payloads: list[dict] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.payloads.append(json)
        return FakeResponse(self.body)


class EmbeddingClientTest(unittest.TestCase):
    def test_batch_remote_embeddings_preserve_order_and_send_dimensions(self) -> None:
        vector_a = [0.1] * 1536
        vector_b = [0.2] * 1536
        client = FakeClient(
            {
                "data": [
                    {"index": 0, "embedding": vector_a},
                    {"index": 1, "embedding": vector_b},
                ]
            }
        )

        with patch.object(embedding.settings, "embedding_provider", "openrouter"), \
            patch.object(embedding.settings, "embedding_api_key", "key"), \
            patch.object(embedding.settings, "embedding_model", "openai/text-embedding-3-small"), \
            patch.object(embedding.settings, "embedding_base_url", "https://openrouter.ai/api/v1"), \
            patch.object(embedding.settings, "embedding_dimensions", 1536), \
            patch("app.embedding.httpx.Client", return_value=client):
            vectors = embedding.embed_texts(["first", "second"])

        self.assertEqual(vectors, [vector_a, vector_b])
        self.assertEqual(client.payloads[0]["model"], "openai/text-embedding-3-small")
        self.assertEqual(client.payloads[0]["input"], ["first", "second"])
        self.assertEqual(client.payloads[0]["dimensions"], 1536)
        self.assertEqual(client.payloads[0]["encoding_format"], "float")

    def test_wrong_remote_dimension_raises_without_local_fallback(self) -> None:
        client = FakeClient({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

        with patch.object(embedding.settings, "embedding_provider", "openrouter"), \
            patch.object(embedding.settings, "embedding_api_key", "key"), \
            patch.object(embedding.settings, "embedding_model", "openai/text-embedding-3-small"), \
            patch.object(embedding.settings, "embedding_base_url", "https://openrouter.ai/api/v1"), \
            patch.object(embedding.settings, "embedding_dimensions", 1536), \
            patch("app.embedding.httpx.Client", return_value=client), \
            patch("app.embedding.time.sleep"):
            with self.assertRaises(EmbeddingProviderError):
                embedding.embed_text("hello")

    def test_local_hash_is_used_when_remote_is_not_configured(self) -> None:
        with patch.object(embedding.settings, "embedding_provider", "local_hash"), \
            patch.object(embedding.settings, "embedding_api_key", ""), \
            patch.object(embedding.settings, "embedding_model", "openai/text-embedding-3-small"), \
            patch.object(embedding.settings, "embedding_dimensions", 1536):
            vector = embedding.embed_text("refund pending")

        self.assertEqual(len(vector), 1536)
        self.assertGreater(sum(abs(value) for value in vector), 0)


if __name__ == "__main__":
    unittest.main()
