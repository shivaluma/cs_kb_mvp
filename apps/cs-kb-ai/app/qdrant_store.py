from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.schemas import RetrievalFilters


_collection_ready = False


class QdrantError(RuntimeError):
    pass


def qdrant_configured() -> bool:
    return settings.vector_backend in {"dual", "qdrant"} and bool(settings.qdrant_url)


def _base_url() -> str:
    return settings.qdrant_url.rstrip("/")


def _headers() -> dict[str, str]:
    if not settings.qdrant_api_key:
        return {}
    return {"api-key": settings.qdrant_api_key}


def _client() -> httpx.Client:
    return httpx.Client(timeout=settings.qdrant_timeout_seconds, headers=_headers())


def ensure_collection() -> None:
    global _collection_ready
    if _collection_ready:
        return
    if not qdrant_configured():
        raise QdrantError("qdrant_not_configured")

    target = f"{_base_url()}/collections/{settings.qdrant_collection}"
    with _client() as client:
        response = client.get(target)
        if response.status_code == 404:
            response = client.put(
                target,
                json={
                    "vectors": {
                        "size": settings.embedding_dimensions,
                        "distance": "Cosine",
                    }
                },
            )
        response.raise_for_status()
    _collection_ready = True


def _match_any(key: str, values: list[str]) -> dict[str, Any]:
    return {"key": key, "match": {"any": values}}


def _match_value(key: str, value: Any) -> dict[str, Any]:
    return {"key": key, "match": {"value": value}}


def _add_list_condition(conditions: list[dict[str, Any]], key: str, values: list[str]) -> None:
    clean_values = [str(value).strip() for value in values if str(value).strip()]
    if clean_values:
        conditions.append(_match_any(key, clean_values))


def build_filter(filters: RetrievalFilters) -> dict[str, Any]:
    statuses = filters.status or ["published"]
    conditions: list[dict[str, Any]] = [
        _match_value("document_status", "active"),
        _match_any("status", [str(status) for status in statuses]),
    ]

    if statuses == ["published"]:
        conditions.extend(
            [
                _match_value("is_current_version", True),
                _match_value("publish_state", "published_ready"),
                _match_value("review_status", "approved"),
                _match_any("extraction_status", ["structured", "manually_curated"]),
                _match_value("publish_blocked", False),
            ]
        )

    _add_list_condition(conditions, "document_id", filters.document_ids)
    _add_list_condition(conditions, "audience", filters.audience)
    _add_list_condition(conditions, "visibility", filters.visibility)
    _add_list_condition(conditions, "scope", filters.scope)
    _add_list_condition(conditions, "policy_type", filters.policy_type)
    _add_list_condition(conditions, "authority_level", filters.authority_level)
    _add_list_condition(conditions, "tags", filters.tags)
    _add_list_condition(conditions, "case_reasons", filters.case_reasons)
    _add_list_condition(conditions, "vertical", filters.vertical)
    _add_list_condition(conditions, "category", filters.category)
    _add_list_condition(conditions, "collections", filters.collections)
    _add_list_condition(conditions, "task_type", filters.task_types)
    _add_list_condition(conditions, "unit_type", filters.unit_types)
    return {"must": conditions}


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_value(metadata: dict[str, Any], keys: list[str], default: Any = "") -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", []):
            return value
    return default


def _list_value(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _merged_list_values(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _list_value(value):
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = parse_metadata(row.get("metadata"))
    collections = _merged_list_values(
        metadata.get("collections"),
        metadata.get("collection_slug"),
        metadata.get("collection"),
    )
    audience = _list_value(_metadata_value(metadata, ["audience"], []))
    return {
        "chunk_id": str(row.get("chunk_id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "version_id": str(row.get("version_id") or ""),
        "title": str(row.get("title") or ""),
        "source_filename": str(row.get("source_filename") or ""),
        "version_number": int(row.get("version_number") or 1),
        "document_status": str(row.get("document_status") or "active"),
        "status": str(row.get("status") or "published"),
        "publish_state": str(row.get("publish_state") or metadata.get("publish_state") or ""),
        "review_status": str(metadata.get("review_status") or row.get("review_status") or ""),
        "extraction_status": str(metadata.get("extraction_status") or ""),
        "publish_blocked": _bool_value(metadata.get("publish_blocked"), False),
        "is_current_version": _bool_value(row.get("is_current_version"), False),
        "chunk_index": int(row.get("chunk_index") or 0),
        "section": str(row.get("section") or ""),
        "heading": str(row.get("heading") or ""),
        "visibility": str(_metadata_value(metadata, ["visibility"], "internal_only")),
        "scope": str(_metadata_value(metadata, ["scope", "retrieval_scope"], "generic")),
        "policy_type": str(_metadata_value(metadata, ["policy_type", "unit_type"], row.get("section") or "")),
        "authority_level": str(_metadata_value(metadata, ["authority_level"], "policy")),
        "risk_level": str(_metadata_value(metadata, ["risk_level"], "")),
        "source_ref_quality": str(_metadata_value(metadata, ["source_ref_quality"], "")),
        "audience": audience,
        "tags": _list_value(metadata.get("tags")),
        "case_reasons": _list_value(metadata.get("case_reasons")),
        "vertical": _list_value(metadata.get("vertical")),
        "category": _list_value(metadata.get("category")),
        "collections": collections,
        "task_type": _list_value(metadata.get("task_type")),
        "unit_type": str(_metadata_value(metadata, ["unit_type"], row.get("section") or "")),
    }


def parse_vector(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text.strip():
        return []
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def upsert_points(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_collection()
    points: list[dict[str, Any]] = []
    for row in rows:
        vector = parse_vector(row.get("embedding"))
        chunk_id = str(row.get("chunk_id") or "")
        if not chunk_id or not vector:
            continue
        points.append(
            {
                "id": chunk_id,
                "vector": vector,
                "payload": payload_from_row(row),
            }
        )
    if not points:
        return 0

    target = f"{_base_url()}/collections/{settings.qdrant_collection}/points"
    with _client() as client:
        response = client.put(target, params={"wait": "true"}, json={"points": points})
        response.raise_for_status()
    return len(points)


def search(vector: list[float], filters: RetrievalFilters, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    ensure_collection()
    target = f"{_base_url()}/collections/{settings.qdrant_collection}/points/search"
    payload = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
        "filter": build_filter(filters),
    }
    with _client() as client:
        response = client.post(target, json=payload)
        response.raise_for_status()
    result = response.json().get("result") or []
    hits: list[dict[str, Any]] = []
    for point in result:
        point_payload = point.get("payload") or {}
        chunk_id = point_payload.get("chunk_id") or point.get("id")
        if not chunk_id:
            continue
        hits.append({"chunk_id": str(chunk_id), "score": float(point.get("score") or 0.0)})
    return hits
