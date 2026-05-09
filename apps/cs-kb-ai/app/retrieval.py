from __future__ import annotations

import time
from typing import Any

from app.embedding import embed_text
from app import repository
from app.schemas import Citation, RetrievalRequest, RetrievalResponse, RetrievalResult
from app.text_processing import expand_query, normalize_phrase, phrase_in_query


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

    if any_phrase(normalized_query, ["order id", "ma don hang"]) and any_phrase(normalized_query, ["huy", "khong cung cap", "co duoc cung cap", "bao mat"]):
        if unit_type == "security_note":
            boost += 0.08
        if phrase_in_query("huy", text) and phrase_in_query("khong cung cap", text):
            boost += 0.03

    if any_phrase(normalized_query, ["khong xac dinh", "khong kiem tra", "khong tim duoc"]):
        if unit_type == "decision_point" and any_phrase(text, ["xac dinh duoc chuyen xe don hang", "kiem tra va xac dinh"]):
            boost += 0.08
        if unit_type == "workflow_step" and any_phrase(text, ["chu dong kiem tra", "gan nhat tren he thong"]):
            boost += 0.07

    if any_phrase(normalized_query, ["khieu nai", "trong vong bao lau", "1h"]) and phrase_in_query("befood", normalized_query):
        if unit_type == "operational_note" and any_phrase(text, ["trong vong 1h", "thoi gian khieu nai"]):
            boost += 0.08

    if phrase_in_query("chat", normalized_query) and any_phrase(normalized_query, ["trip id", "order id"]):
        if unit_type == "workflow_step" and phrase_in_query("khung chat", text):
            boost += 0.08

    if any_phrase(normalized_query, ["chuyen khac", "don hang khac", "xin thong tin"]):
        if unit_type == "workflow_step" and any_phrase(text, ["xin ten nha hang", "xin trip id order id"]):
            boost += 0.08
        if unit_type == "decision_point" and any_phrase(text, ["chuyen xe don hang khac", "buoc 3 1"]):
            boost += 0.05

    if any_phrase(normalized_query, ["script", "macro", "phan hoi mau"]):
        if unit_type == "macro_script":
            boost += 0.06
    elif unit_type == "macro_script":
        boost -= 0.015

    return boost


def any_phrase(haystack: str, phrases: list[str]) -> bool:
    return any(phrase_in_query(normalize_phrase(phrase), haystack) for phrase in phrases)


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
