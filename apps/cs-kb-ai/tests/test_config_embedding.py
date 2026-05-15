import os
import unittest
from unittest.mock import patch

from app.config import DEFAULT_EMBEDDING_MODEL, Settings


class EmbeddingConfigTest(unittest.TestCase):
    def test_embedding_config_falls_back_to_openrouter_env(self) -> None:
        env = {
            "OPENROUTER_API_KEY": "openrouter-key",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            "EMBEDDING_BASE_URL": "",
            "EMBEDDING_API_KEY": "",
            "EMBEDDING_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        self.assertEqual(settings.embedding_api_key, "openrouter-key")
        self.assertEqual(settings.embedding_base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(settings.embedding_model, DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(settings.embedding_provider, "openrouter")
        self.assertEqual(settings.embedding_dimensions, 1536)

    def test_embedding_config_uses_local_hash_without_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.embedding_provider, "local_hash")
        self.assertEqual(settings.embedding_model, DEFAULT_EMBEDDING_MODEL)


if __name__ == "__main__":
    unittest.main()
