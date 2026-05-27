from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.text_processing import tokenize


LOCAL_EMBEDDING_PROVIDERS = {"", "local", "local_hash"}
MAX_EMBEDDING_INPUT_CHARS = 12000
EMBEDDING_RETRY_COUNT = 3


class EmbeddingProviderError(RuntimeError):
    pass


def embed_text(text: str, dimensions: int | None = None) -> list[float]:
    return embed_texts([text], dimensions=dimensions)[0]


def embed_texts(texts: list[str], dimensions: int | None = None) -> list[list[float]]:
    dims = dimensions or settings.embedding_dimensions
    if not texts:
        return []
    if remote_embedding_configured():
        return remote_embeddings(texts, dims)
    return [local_hash_embedding(text, dims) for text in texts]


def remote_embedding_configured() -> bool:
    return (
        settings.embedding_provider not in LOCAL_EMBEDDING_PROVIDERS
        and bool(settings.embedding_api_key)
        and bool(settings.embedding_model)
    )


def embedding_runtime_metadata() -> dict[str, object]:
    remote_enabled = remote_embedding_configured()
    provider = settings.embedding_provider if remote_enabled else "local_hash"
    model = settings.embedding_model if remote_enabled else "local_hash"
    dimensions = settings.embedding_dimensions
    return {
        "embedding_provider": provider,
        "embedding_model": model,
        "embedding_dimensions": dimensions,
        "embedding_spec_id": embedding_spec_id(provider, model, dimensions),
        "embedded_at": datetime.now(timezone.utc).isoformat(),
    }


def embedding_spec_id(provider: str, model: str, dimensions: int) -> str:
    return f"{provider}:{model}:{dimensions}"


def local_hash_embedding(text: str, dims: int) -> list[float]:
    vector = [0.0] * dims
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def remote_embedding(text: str) -> list[float]:
    return remote_embeddings([text], settings.embedding_dimensions)[0]


def remote_embeddings(texts: list[str], dims: int) -> list[list[float]]:
    base_url = settings.embedding_base_url.rstrip("/")
    payload = {
        "model": settings.embedding_model,
        "input": [(text or "")[:MAX_EMBEDDING_INPUT_CHARS] for text in texts],
        "dimensions": dims,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(EMBEDDING_RETRY_COUNT):
        try:
            with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
                response = client.post(f"{base_url}/embeddings", headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
            return parse_embedding_response(body, len(texts), dims)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            last_error = exc
            if attempt < EMBEDDING_RETRY_COUNT - 1:
                time.sleep(0.35 * (2**attempt))

    raise EmbeddingProviderError(f"embedding_provider_unavailable: {last_error}") from last_error


def parse_embedding_response(body: object, expected_count: int, dims: int) -> list[list[float]]:
    if not isinstance(body, dict):
        raise ValueError("embedding_response_not_object")
    data = body.get("data")
    if not isinstance(data, list) or len(data) != expected_count:
        raise ValueError("embedding_response_count_mismatch")

    vectors: list[list[float] | None] = [None] * expected_count
    for fallback_index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("embedding_response_item_not_object")
        raw_index = item.get("index", fallback_index)
        if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= expected_count:
            raise ValueError("embedding_response_invalid_index")
        vectors[raw_index] = validate_embedding_vector(item.get("embedding"), dims)

    if any(vector is None for vector in vectors):
        raise ValueError("embedding_response_missing_index")
    return [vector for vector in vectors if vector is not None]


def validate_embedding_vector(value: object, dims: int) -> list[float]:
    if not isinstance(value, list):
        raise ValueError("embedding_response_missing_vector")
    if len(value) != dims:
        raise ValueError(f"embedding_dimension_mismatch:{len(value)}:{dims}")
    return [float(item) for item in value]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
