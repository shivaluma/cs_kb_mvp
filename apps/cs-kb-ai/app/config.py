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


settings = Settings()
