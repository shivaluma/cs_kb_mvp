from __future__ import annotations

import os


EMBEDDING_DIMENSIONS = 384


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgres://cs_kb:cs_kb@localhost:5432/cs_kb?sslmode=disable",
        )
        self.embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
        self.chunk_target_tokens = int(os.getenv("CHUNK_TARGET_TOKENS", "260"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "48"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
        self.openrouter_extraction_model = os.getenv("OPENROUTER_EXTRACTION_MODEL", self.openrouter_model)
        self.openrouter_vision_model = os.getenv("OPENROUTER_VISION_MODEL", self.openrouter_extraction_model)
        self.openrouter_metadata_model = os.getenv("OPENROUTER_METADATA_MODEL", self.openrouter_model)
        self.openrouter_chat_model = os.getenv("OPENROUTER_CHAT_MODEL", self.openrouter_model)
        self.openrouter_chat_simple_model = os.getenv(
            "OPENROUTER_CHAT_SIMPLE_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_SIMPLE", "google/gemini-2.5-flash-lite"),
        ).strip()
        self.openrouter_chat_policy_model = os.getenv(
            "OPENROUTER_CHAT_POLICY_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_POLICY", "deepseek/deepseek-v3.2"),
        ).strip()
        self.openrouter_chat_high_risk_model = os.getenv(
            "OPENROUTER_CHAT_HIGH_RISK_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_HIGH_RISK", "deepseek/deepseek-v3.2"),
        ).strip()
        self.openrouter_chat_complex_model = os.getenv(
            "OPENROUTER_CHAT_COMPLEX_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_COMPLEX", "moonshotai/kimi-k2.6"),
        ).strip()
        self.openrouter_chat_fallback_model = os.getenv(
            "OPENROUTER_CHAT_FALLBACK_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_FALLBACK", "moonshotai/kimi-k2.6"),
        ).strip()
        self.openrouter_timeout_seconds = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
        self.public_app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:3000")
        self.qdrant_url = os.getenv("QDRANT_URL", "").strip()
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local_hash").strip().lower()
        self.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", self.openrouter_base_url).strip()
        self.embedding_api_key = os.getenv("EMBEDDING_API_KEY", self.openrouter_api_key).strip()
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "").strip()


settings = Settings()
