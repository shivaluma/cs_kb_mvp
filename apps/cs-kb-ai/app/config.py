from __future__ import annotations

import os


EMBEDDING_DIMENSIONS = 1536
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EXTRACT_PIPELINE_MODEL = "anthropic/claude-3.5-haiku"
DEPRECATED_EXTRACT_PIPELINE_MODELS = {"google/gemini-3-flash-preview"}


def first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def normalize_extract_pipeline_model(value: str | None, fallback: str = DEFAULT_EXTRACT_PIPELINE_MODEL) -> str:
    model = (value or "").strip() or fallback
    return DEFAULT_EXTRACT_PIPELINE_MODEL if model in DEPRECATED_EXTRACT_PIPELINE_MODELS else model


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgres://cs_kb:cs_kb@localhost:5432/cs_kb?sslmode=disable",
        )
        self.chunk_target_tokens = int(os.getenv("CHUNK_TARGET_TOKENS", "260"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "48"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
        self.openrouter_extraction_model = normalize_extract_pipeline_model(
            os.getenv("OPENROUTER_EXTRACTION_MODEL", ""),
            DEFAULT_EXTRACT_PIPELINE_MODEL,
        )
        self.openrouter_refine_model = normalize_extract_pipeline_model(
            os.getenv("OPENROUTER_REFINE_MODEL", ""),
            DEFAULT_EXTRACT_PIPELINE_MODEL,
        )
        self.openrouter_vision_model = normalize_extract_pipeline_model(
            os.getenv("OPENROUTER_VISION_MODEL", ""),
            self.openrouter_refine_model,
        )
        self.openrouter_metadata_model = os.getenv("OPENROUTER_METADATA_MODEL", self.openrouter_model)
        self.openrouter_chat_model = os.getenv("OPENROUTER_CHAT_MODEL", self.openrouter_model)
        self.openrouter_chat_simple_model = os.getenv(
            "OPENROUTER_CHAT_SIMPLE_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_SIMPLE", "google/gemini-2.5-flash-lite"),
        ).strip()
        self.openrouter_chat_policy_model = os.getenv(
            "OPENROUTER_CHAT_POLICY_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_POLICY", "moonshotai/kimi-k2.5"),
        ).strip()
        self.openrouter_chat_high_risk_model = os.getenv(
            "OPENROUTER_CHAT_HIGH_RISK_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_HIGH_RISK", "moonshotai/kimi-k2.5"),
        ).strip()
        self.openrouter_chat_complex_model = os.getenv(
            "OPENROUTER_CHAT_COMPLEX_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_COMPLEX", "moonshotai/kimi-k2.6"),
        ).strip()
        self.openrouter_chat_fallback_model = os.getenv(
            "OPENROUTER_CHAT_FALLBACK_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_FALLBACK", "moonshotai/kimi-k2.6"),
        ).strip()
        self.openrouter_chat_gemini_25_flash_model = os.getenv(
            "OPENROUTER_CHAT_GEMINI_25_FLASH_MODEL",
            "google/gemini-2.5-flash",
        ).strip()
        self.openrouter_chat_gemini_3_flash_model = os.getenv(
            "OPENROUTER_CHAT_GEMINI_3_FLASH_MODEL",
            "google/gemini-3-flash-preview",
        ).strip()
        self.openrouter_chat_claude_35_haiku_model = os.getenv(
            "OPENROUTER_CHAT_CLAUDE_35_HAIKU_MODEL",
            "anthropic/claude-3.5-haiku",
        ).strip()
        self.openrouter_timeout_seconds = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
        self.public_app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:3000")
        self.qdrant_url = os.getenv("QDRANT_URL", "").strip()
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()
        self.embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
        self.embedding_base_url = first_non_empty(os.getenv("EMBEDDING_BASE_URL"), self.openrouter_base_url)
        self.embedding_api_key = first_non_empty(os.getenv("EMBEDDING_API_KEY"), self.openrouter_api_key)
        self.embedding_model = first_non_empty(os.getenv("EMBEDDING_MODEL"), DEFAULT_EMBEDDING_MODEL)
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
        self.embedding_provider = embedding_provider or ("openrouter" if self.embedding_api_key else "local_hash")


settings = Settings()
