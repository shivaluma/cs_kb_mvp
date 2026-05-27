from __future__ import annotations

import os


EMBEDDING_DIMENSIONS = 1536
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_DOCUMENT_PARSER_MODEL = "google/gemini-3.1-flash-lite-preview"
ADMIN_RESET_CONFIRMATION = "RESET CS KB DATA"


def first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgres://cs_kb:cs_kb@localhost:5432/cs_kb?sslmode=disable",
        )
        self.chunk_target_tokens = int(os.getenv("CHUNK_TARGET_TOKENS", "260"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "48"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", DEFAULT_DOCUMENT_PARSER_MODEL)
        self.openrouter_extraction_model = os.getenv("OPENROUTER_EXTRACTION_MODEL", self.openrouter_model).strip() or self.openrouter_model
        self.openrouter_refine_model = os.getenv(
            "OPENROUTER_REFINE_MODEL",
            DEFAULT_DOCUMENT_PARSER_MODEL,
        ).strip()
        self.openrouter_vision_model = (
            os.getenv("OPENROUTER_VISION_MODEL", "").strip()
            or self.openrouter_refine_model
        )
        self.openrouter_metadata_model = os.getenv("OPENROUTER_METADATA_MODEL", self.openrouter_model)
        self.openrouter_chat_model = os.getenv("OPENROUTER_CHAT_MODEL", self.openrouter_model)
        self.openrouter_chat_simple_model = os.getenv(
            "OPENROUTER_CHAT_SIMPLE_MODEL",
            os.getenv("OPENROUTER_CHAT_MODEL_SIMPLE", DEFAULT_DOCUMENT_PARSER_MODEL),
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
            DEFAULT_DOCUMENT_PARSER_MODEL,
        ).strip()
        self.openrouter_chat_claude_35_haiku_model = os.getenv(
            "OPENROUTER_CHAT_CLAUDE_35_HAIKU_MODEL",
            "anthropic/claude-3.5-haiku",
        ).strip()
        self.openrouter_timeout_seconds = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
        self.openrouter_reasoning_effort = os.getenv("OPENROUTER_REASONING_EFFORT", "low").strip().lower()
        self.meili_host = os.getenv("MEILI_HOST", "").strip()
        self.meili_master_key = os.getenv("MEILI_MASTER_KEY", "dev_master_key").strip()
        self.ranking_config_path = os.getenv("SOP_RANKING_CONFIG_PATH", "").strip()
        self.rerank_provider = os.getenv("RERANK_PROVIDER", "none").strip().lower()
        self.rerank_enable_for_portal = env_bool("RERANK_ENABLE_FOR_PORTAL", False)
        self.rerank_enable_for_ai_chat = env_bool("RERANK_ENABLE_FOR_AI_CHAT", True)
        self.rerank_max_candidates = int(os.getenv("RERANK_MAX_CANDIDATES", "15"))
        self.rerank_timeout_ms = int(os.getenv("RERANK_TIMEOUT_MS", "3000"))
        self.rerank_cache_ttl_seconds = int(os.getenv("RERANK_CACHE_TTL_SECONDS", "86400"))
        self.rerank_model_name = os.getenv("RERANK_MODEL_NAME", "").strip()
        self.rerank_prompt_version = os.getenv("RERANK_PROMPT_VERSION", "v1").strip()
        self.rerank_custom_url = os.getenv("RERANK_CUSTOM_URL", "").strip()
        self.cohere_api_key = os.getenv("COHERE_API_KEY", "").strip()
        self.public_app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:3000")
        self.qdrant_url = os.getenv("QDRANT_URL", "").strip()
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()
        vector_backend = os.getenv("VECTOR_BACKEND", "dual").strip().lower()
        if vector_backend not in {"pgvector", "qdrant", "dual"}:
            vector_backend = "dual"
        self.vector_backend = vector_backend
        self.qdrant_collection = os.getenv("QDRANT_COLLECTION", "sop_chunks").strip() or "sop_chunks"
        self.qdrant_timeout_seconds = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "3"))
        self.embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
        self.embedding_base_url = first_non_empty(os.getenv("EMBEDDING_BASE_URL"), self.openrouter_base_url)
        self.embedding_api_key = first_non_empty(os.getenv("EMBEDDING_API_KEY"), self.openrouter_api_key)
        self.embedding_model = first_non_empty(os.getenv("EMBEDDING_MODEL"), DEFAULT_EMBEDDING_MODEL)
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
        self.embedding_provider = embedding_provider or ("openrouter" if self.embedding_api_key else "local_hash")
        self.admin_reset_enabled = env_bool("CS_KB_ENABLE_MAGIC_RESET", False)
        self.admin_reset_confirmation = (
            os.getenv("CS_KB_ADMIN_RESET_CONFIRMATION", ADMIN_RESET_CONFIRMATION).strip()
            or ADMIN_RESET_CONFIRMATION
        )


settings = Settings()
