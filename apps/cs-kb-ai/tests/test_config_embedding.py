import os
import unittest
from unittest.mock import patch

from app.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_EXTRACT_PIPELINE_MODEL, Settings


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

    def test_extraction_pipeline_defaults_to_claude_haiku(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.openrouter_extraction_model, DEFAULT_EXTRACT_PIPELINE_MODEL)
        self.assertEqual(settings.openrouter_refine_model, DEFAULT_EXTRACT_PIPELINE_MODEL)
        self.assertEqual(settings.openrouter_vision_model, DEFAULT_EXTRACT_PIPELINE_MODEL)

    def test_extraction_pipeline_maps_deprecated_gemini_3_preview_to_claude_haiku(self) -> None:
        env = {
            "OPENROUTER_EXTRACTION_MODEL": "google/gemini-3-flash-preview",
            "OPENROUTER_REFINE_MODEL": "google/gemini-3-flash-preview",
            "OPENROUTER_VISION_MODEL": "google/gemini-3-flash-preview",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        self.assertEqual(settings.openrouter_extraction_model, DEFAULT_EXTRACT_PIPELINE_MODEL)
        self.assertEqual(settings.openrouter_refine_model, DEFAULT_EXTRACT_PIPELINE_MODEL)
        self.assertEqual(settings.openrouter_vision_model, DEFAULT_EXTRACT_PIPELINE_MODEL)


if __name__ == "__main__":
    unittest.main()
