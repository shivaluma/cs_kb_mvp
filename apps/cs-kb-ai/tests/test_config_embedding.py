import os
import unittest
from unittest.mock import patch

from app.config import ADMIN_RESET_CONFIRMATION, DEFAULT_EMBEDDING_MODEL, Settings


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

    def test_openrouter_api_key_is_stripped(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "  openrouter-key\n"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.openrouter_api_key, "openrouter-key")
        self.assertEqual(settings.embedding_api_key, "openrouter-key")

    def test_magic_reset_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertFalse(settings.admin_reset_enabled)
        self.assertEqual(settings.admin_reset_confirmation, ADMIN_RESET_CONFIRMATION)

    def test_magic_reset_requires_explicit_enable(self) -> None:
        with patch.dict(os.environ, {"CS_KB_ENABLE_MAGIC_RESET": "true"}, clear=True):
            settings = Settings()

        self.assertTrue(settings.admin_reset_enabled)


if __name__ == "__main__":
    unittest.main()
