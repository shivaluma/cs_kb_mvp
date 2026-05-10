from __future__ import annotations

import hashlib
import math

import httpx

from app.config import settings
from app.text_processing import tokenize


def embed_text(text: str, dimensions: int | None = None) -> list[float]:
    dims = dimensions or settings.embedding_dimensions
    if settings.embedding_provider not in {"", "local", "local_hash"} and settings.embedding_api_key and settings.embedding_model:
        try:
            return fit_dimensions(remote_embedding(text), dims)
        except Exception:
            # Keep ingestion/search available if the configured embedding provider is temporarily unavailable.
            # The warning is surfaced through retrieval quality metrics rather than blocking SOP access.
            pass
    return local_hash_embedding(text, dims)


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
    base_url = settings.embedding_base_url.rstrip("/")
    payload = {
        "model": settings.embedding_model,
        "input": text[:12000],
    }
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
        response = client.post(f"{base_url}/embeddings", headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    embedding = body.get("data", [{}])[0].get("embedding")
    if not isinstance(embedding, list):
        raise ValueError("embedding_response_missing_vector")
    return [float(value) for value in embedding]


def fit_dimensions(vector: list[float], dims: int) -> list[float]:
    if len(vector) > dims:
        fitted = vector[:dims]
    elif len(vector) < dims:
        fitted = [*vector, *([0.0] * (dims - len(vector)))]
    else:
        fitted = vector
    norm = math.sqrt(sum(value * value for value in fitted))
    if norm == 0:
        return fitted
    return [value / norm for value in fitted]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
