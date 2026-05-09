from __future__ import annotations

import time
from typing import Any

from app.embedding import embed_text
from app import repository
from app.schemas import Citation, RetrievalRequest, RetrievalResponse, RetrievalResult
from app.text_processing import expand_query


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
        fused_rows = rows_from_single_mode(lexical_rows, "lexical", request.limit)
    elif request.mode == "vector":
        fused_rows = rows_from_single_mode(vector_rows, "vector", request.limit)
    else:
        fused_rows = reciprocal_rank_fusion(lexical_rows, vector_rows, request.limit)

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
