from __future__ import annotations

import time
from typing import Any

from app.embedding import embed_text
from app import repository
from app.schemas import Citation, RetrievalRequest, RetrievalResponse, RetrievalResult
from app.text_processing import expand_query, normalize_phrase


RRF_K = 60


def retrieve(request: RetrievalRequest) -> RetrievalResponse:
    started_at = time.perf_counter()
    synonym_groups = repository.active_synonym_groups()
    normalized_query, expansions, matched_synonyms = expand_query(request.query, synonym_groups)
    query_expansion = {
        "strategy": "db_managed_synonyms",
        "expansions": expansions,
        "matched_synonyms": matched_synonyms,
        "active_synonym_group_count": len(synonym_groups),
    }
    warnings: list[str] = []

    if not normalized_query:
        latency_ms = repository.log_retrieval(
            request.query,
            request.filters.model_dump(),
            request.mode,
            0,
            started_at,
        )
        return RetrievalResponse(
            query=request.query,
            normalized_query=normalized_query,
            query_expansion=query_expansion,
            mode=request.mode,
            results=[],
            citations=[],
            warnings=["empty_query"],
            latency_ms=latency_ms,
        )

    lexical_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    search_limit = max(request.limit * 4, 20)

    if request.mode in {"lexical", "hybrid"}:
        lexical_rows = repository.lexical_search(normalized_query, request.filters, search_limit)
    if request.mode in {"vector", "hybrid"}:
        vector_rows = repository.vector_search(embed_text(normalized_query), request.filters, search_limit)

    if request.mode == "lexical":
        fused_rows = rows_from_single_mode(lexical_rows, "lexical", search_limit)
    elif request.mode == "vector":
        fused_rows = rows_from_single_mode(vector_rows, "vector", search_limit)
    else:
        fused_rows = reciprocal_rank_fusion(lexical_rows, vector_rows, search_limit)

    fused_rows = rerank_by_query_intent(normalized_query, fused_rows)[: request.limit]
    fused_rows = [row for row in fused_rows if is_reliable(row)]
    relation_rows = repository.approved_relation_target_rows(
        [str(row.get("document_id") or "") for row in fused_rows],
        [str(row.get("chunk_id") or "") for row in fused_rows],
        min(2, request.limit),
    )
    if relation_rows:
        fused_rows = [*fused_rows, *relation_rows]
    if not fused_rows:
        warnings.append("no_reliable_source")

    latency_ms = repository.log_retrieval(
        request.query,
        request.filters.model_dump(),
        request.mode,
        len(fused_rows),
        started_at,
    )
    results = [to_result(row) for row in fused_rows]
    return RetrievalResponse(
        query=request.query,
        normalized_query=normalized_query,
        query_expansion=query_expansion,
        mode=request.mode,
        results=results,
        citations=[result.citation for result in results],
        warnings=warnings,
        latency_ms=latency_ms,
    )


def rows_from_single_mode(rows: list[dict[str, Any]], mode: str, limit: int) -> list[dict[str, Any]]:
    output = []
    for rank, row in enumerate(rows[:limit], start=1):
        item = dict(row)
        item["score"] = float(row.get("score") or 0)
        item["lexical_score"] = float(row.get("score") or 0) if mode == "lexical" else 0.0
        item["vector_score"] = float(row.get("score") or 0) if mode == "vector" else 0.0
        item["rank_source"] = [mode]
        item["rrf_rank"] = rank
        output.append(item)
    return output


def reciprocal_rank_fusion(
    lexical_rows: list[dict[str, Any]],
    vector_rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    by_chunk: dict[str, dict[str, Any]] = {}

    def absorb(rows: list[dict[str, Any]], source: str) -> None:
        for rank, row in enumerate(rows, start=1):
            chunk_id = str(row["chunk_id"])
            item = by_chunk.setdefault(
                chunk_id,
                {
                    **row,
                    "score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.0,
                    "rank_source": [],
                    "best_rank": rank,
                },
            )
            item["score"] += 1.0 / (RRF_K + rank)
            item["best_rank"] = min(item["best_rank"], rank)
            item["rank_source"].append(source)
            if source == "lexical":
                item["lexical_score"] = max(float(row.get("score") or 0), item["lexical_score"])
            else:
                item["vector_score"] = max(float(row.get("score") or 0), item["vector_score"])

    absorb(lexical_rows, "lexical")
    absorb(vector_rows, "vector")

    return sorted(
        by_chunk.values(),
        key=lambda item: (item["score"], item["lexical_score"], item["vector_score"], -item["best_rank"]),
        reverse=True,
    )[:limit]


def rerank_by_query_intent(normalized_query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        item = dict(row)
        boost = intent_boost(normalized_query, item)
        if boost:
            item["score"] = float(item.get("score") or 0) + boost
            item["intent_boost"] = round(boost, 4)
        output.append(item)
    return sorted(
        output,
        key=lambda item: (
            float(item.get("score") or 0),
            float(item.get("intent_boost") or 0),
            float(item.get("lexical_score") or 0),
            float(item.get("vector_score") or 0),
            -int(item.get("best_rank") or item.get("rrf_rank") or 999),
        ),
        reverse=True,
    )


def intent_boost(normalized_query: str, row: dict[str, Any]) -> float:
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    unit_type = str(metadata.get("unit_type") or row.get("section") or "").strip()
    text = normalize_phrase(" ".join([str(row.get("heading") or ""), str(row.get("content") or "")]))
    boost = 0.0

    query_tokens = set(token for token in normalized_query.split() if len(token) >= 3)
    metadata_text = normalize_phrase(" ".join(flatten_metadata_terms(metadata)))
    metadata_tokens = set(token for token in metadata_text.split() if len(token) >= 3)
    text_tokens = set(token for token in text.split() if len(token) >= 3)

    metadata_overlap = len(query_tokens & metadata_tokens)
    text_overlap = len(query_tokens & text_tokens)
    if metadata_overlap:
        boost += min(0.12, metadata_overlap * 0.018)
    if text_overlap:
        boost += min(0.05, text_overlap * 0.006)

    action_unit_types = {
        "validation_rule",
        "handling_rule",
        "routing_rule",
        "operational_instruction",
        "policy_rule",
        "exception_rule",
        "threshold_rule",
        "sla_rule",
        "decision_rule",
        "escalation_rule",
        "case_creation_rule",
        "handoff_rule",
        "decision_point",
        "workflow_step",
        "macro_script",
        "security_note",
        "compliance_note",
        "warning",
    }
    if unit_type in action_unit_types and metadata_overlap:
        boost += 0.025

    if unit_type in action_unit_types and text_overlap:
        coverage = text_overlap / max(1, len(query_tokens))
        boost += min(0.18, coverage * 0.12)

    if normalized_query and normalized_query in text:
        boost += 0.18

    if has_prohibition_intent(normalized_query) and has_prohibition_answer(text):
        boost += 0.28
        if unit_type in {"security_note", "compliance_note", "warning", "operational_note", "policy_rule", "exception_rule"}:
            boost += 0.08

    if any(token in query_tokens for token in {"zt", "bao", "mat", "security", "compliance", "khong", "cam"}) and unit_type in {"security_note", "compliance_note", "warning", "operational_note"}:
        boost += 0.06

    risk_level = normalize_phrase(str(metadata.get("risk_level") or ""))
    if risk_level in {"high", "critical"} and any(token in query_tokens for token in {"risk", "rui", "ro", "bao", "mat", "security", "compliance", "tuan", "thu"}):
        boost += 0.025

    return boost


def has_prohibition_intent(normalized_query: str) -> bool:
    if not normalized_query:
        return False
    tokens = set(normalized_query.split())
    if {"khong", "cung", "cap"} <= tokens:
        return True
    if {"khong", "duoc"} <= tokens:
        return True
    if "cam" in tokens:
        return True
    return ("zt" in tokens or "bao mat" in normalized_query) and any(term in normalized_query for term in ["order id", "trip id", "cung cap", "bao mat", "zt"])


def has_prohibition_answer(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    if "khong cung cap" in normalized_text:
        return True
    if "khong duoc" in normalized_text:
        return True
    if "zt" in normalized_text and ("bao mat" in normalized_text or "cung cap" in normalized_text):
        return True
    return False


def flatten_metadata_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        terms: list[str] = []
        for item in value:
            terms.extend(flatten_metadata_terms(item))
        return terms
    if isinstance(value, dict):
        terms = []
        for key, item in value.items():
            terms.append(str(key))
            terms.extend(flatten_metadata_terms(item))
        return terms
    return [str(value)]


def to_result(row: dict[str, Any]) -> RetrievalResult:
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    citation = Citation(
        document_id=str(row["document_id"]),
        version_id=str(row["version_id"]),
        chunk_id=str(row["chunk_id"]),
        chunk_index=int(row["chunk_index"]),
        section=str(row["section"]),
        title=str(row["title"]),
        version_number=int(row["version_number"]),
        source_filename=str(row["source_filename"]),
    )

    return RetrievalResult(
        document_id=citation.document_id,
        version_id=citation.version_id,
        chunk_id=citation.chunk_id,
        title=citation.title,
        source_filename=citation.source_filename,
        version_number=citation.version_number,
        chunk_index=citation.chunk_index,
        section=citation.section,
        heading=str(row.get("heading") or ""),
        content=str(row["content"]),
        score=round(float(row.get("score") or 0), 8),
        lexical_score=round(float(row.get("lexical_score") or 0), 8),
        vector_score=round(float(row.get("vector_score") or 0), 8),
        rank_source=list(dict.fromkeys(row.get("rank_source") or [])),
        metadata=metadata,
        citation=citation,
    )


def is_reliable(row: dict[str, Any]) -> bool:
    lexical_score = float(row.get("lexical_score") or 0)
    vector_score = float(row.get("vector_score") or 0)
    rank_sources = row.get("rank_source") or []
    if lexical_score > 0:
        return True
    if "vector" in rank_sources and vector_score >= 0.12:
        return True
    return False
