from __future__ import annotations

import re
import time
import unicodedata
import logging
from typing import Any

import httpx

from app.config import settings
from app.embedding import EmbeddingProviderError, embed_text
from app import repository
from app.ranking import (
    RankingOptions,
    business_rerank,
    candidates_from_rows,
    load_ranking_config,
    maybe_model_rerank,
    merge_candidates,
    mode_config,
    rows_from_candidates,
    understand_query,
)
from app.search_labels import is_bad_search_label
from app.schemas import (
    Citation,
    CollectionRef,
    DisplayBlock,
    DisplayContext,
    DisplayHighlight,
    MatchedChunkContext,
    ParentResultContext,
    RetrievalFilters,
    RetrievalDisplayContract,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    ScrollTarget,
    SourceAnchor,
)
from app.text_processing import expand_query, normalize_phrase


RRF_K = 60
logger = logging.getLogger("cs_kb_ai.retrieval")


def retrieve(request: RetrievalRequest, include_relation_expansion: bool = True) -> RetrievalResponse:
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
        trace = retrieval_trace_payload(
            query_expansion=query_expansion,
            ranking_debug={"ranking_mode": request.ranking_mode, "input_guard": "empty_query"},
            warnings=["empty_query"],
            selected_rows=[],
        )
        latency_ms = repository.log_retrieval(
            request.query,
            request.filters.model_dump(),
            request.mode,
            0,
            started_at,
            trace=trace,
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

    ranking_config = load_ranking_config()
    ranking_mode = request.ranking_mode
    ranking_mode_config = mode_config(ranking_config, ranking_mode)
    ranking_debug: dict[str, Any] = {}
    lexical_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    if ranking_mode == "ai_chat":
        keyword_limit = int(ranking_mode_config.get("keyword_candidate_limit") or max(request.limit * 4, 20))
        vector_limit = int(ranking_mode_config.get("vector_candidate_limit") or max(request.limit * 4, 20))
        merged_limit = int(ranking_mode_config.get("merged_candidate_limit") or max(request.limit * 5, 30))
        business_limit = int(ranking_mode_config.get("business_rerank_limit") or max(request.limit * 2, 20))
    else:
        candidate_limit = int(ranking_mode_config.get("candidate_limit") or max(request.limit * 4, 20))
        keyword_limit = candidate_limit
        vector_limit = candidate_limit
        merged_limit = candidate_limit
        business_limit = max(request.limit, int(ranking_mode_config.get("output_limit") or request.limit))

    query_understanding = understand_query(normalized_query, ranking_mode, ranking_config)
    warnings.extend(query_understanding.warnings)
    candidate_filters, applied_query_filters = filters_with_query_understanding(request.filters, query_understanding, ranking_mode)

    if request.mode in {"lexical", "hybrid"}:
        lexical_rows, keyword_warning = keyword_candidate_rows(normalized_query, candidate_filters, keyword_limit, request.debug)
        if not lexical_rows and applied_query_filters:
            lexical_rows, keyword_warning = keyword_candidate_rows(normalized_query, request.filters, keyword_limit, request.debug)
            warnings.append("query_understanding_filters_relaxed:no_keyword_candidates")
        if keyword_warning:
            warnings.append(keyword_warning)
    if request.mode in {"vector", "hybrid"}:
        try:
            vector = embed_text(normalized_query)
            vector_rows = repository.vector_search(vector, candidate_filters, vector_limit)
            if not vector_rows and applied_query_filters:
                vector_rows = repository.vector_search(vector, request.filters, vector_limit)
                warnings.append("query_understanding_filters_relaxed:no_vector_candidates")
        except EmbeddingProviderError:
            warnings.append("embedding_unavailable")
            if request.mode == "vector":
                trace_warnings = [*warnings, "no_reliable_source"]
                trace = retrieval_trace_payload(
                    query_expansion=query_expansion,
                    ranking_debug={
                        "ranking_mode": ranking_mode,
                        "keyword_candidate_count": len(lexical_rows),
                        "vector_candidate_count": 0,
                        "vector_failure": "embedding_unavailable",
                    },
                    warnings=trace_warnings,
                    selected_rows=[],
                )
                latency_ms = repository.log_retrieval(
                    request.query,
                    retrieval_log_filters(request.filters, candidate_filters, applied_query_filters),
                    request.mode,
                    0,
                    started_at,
                    trace=trace,
                )
                return RetrievalResponse(
                    query=request.query,
                    normalized_query=normalized_query,
                    query_expansion=query_expansion,
                    mode=request.mode,
                    results=[],
                    citations=[],
                    warnings=[*warnings, "no_reliable_source"],
                    latency_ms=latency_ms,
                )
        except Exception as exc:
            warnings.append(f"vector_search_failed:{exc.__class__.__name__}")
            if request.mode == "vector":
                trace_warnings = [*warnings, "no_reliable_source"]
                trace = retrieval_trace_payload(
                    query_expansion=query_expansion,
                    ranking_debug={
                        "ranking_mode": ranking_mode,
                        "keyword_candidate_count": len(lexical_rows),
                        "vector_candidate_count": 0,
                        "vector_failure": exc.__class__.__name__,
                    },
                    warnings=trace_warnings,
                    selected_rows=[],
                )
                latency_ms = repository.log_retrieval(
                    request.query,
                    retrieval_log_filters(request.filters, candidate_filters, applied_query_filters),
                    request.mode,
                    0,
                    started_at,
                    trace=trace,
                )
                return RetrievalResponse(
                    query=request.query,
                    normalized_query=normalized_query,
                    query_expansion=query_expansion,
                    mode=request.mode,
                    results=[],
                    citations=[],
                    warnings=[*warnings, "no_reliable_source"],
                    latency_ms=latency_ms,
                )

    ranking_options = RankingOptions(
        mode=ranking_mode,
        debug=request.debug,
        query_understanding=query_understanding,
        force_model_rerank=request.use_model_rerank,
    )
    if request.mode == "lexical":
        candidates = candidates_from_rows(lexical_rows, "meilisearch" if any(row.get("from_meilisearch") for row in lexical_rows) else "lexical")
    elif request.mode == "vector":
        candidates = candidates_from_rows(vector_rows, "vector")
    else:
        keyword_source = "meilisearch" if any(row.get("from_meilisearch") for row in lexical_rows) else "lexical"
        candidates = merge_candidates(
            candidates_from_rows(lexical_rows, keyword_source),
            candidates_from_rows(vector_rows, "vector"),
            merged_limit,
            ranking_config,
        )

    business_ranked = business_rerank(normalized_query, candidates, ranking_options, ranking_config)[:business_limit]
    model_ranked, rerank_decision = maybe_model_rerank(normalized_query, business_ranked, ranking_options, ranking_config)
    fused_rows = rows_from_candidates(model_ranked[: request.limit], debug=request.debug)
    ranking_debug = {
        "ranking_mode": ranking_mode,
        "intent": query_understanding.intent,
        "query_understanding_used": query_understanding.source == "model",
        "keyword_candidate_count": len(lexical_rows),
        "vector_candidate_count": len(vector_rows),
        "merged_candidate_count": len(candidates),
        "business_candidate_count": len(business_ranked),
        "model_rerank": rerank_decision,
        "query_understanding_filters": applied_query_filters,
        "top_before_business_rerank": candidates[0].chunk_id if candidates else "",
        "top_after_business_rerank": business_ranked[0].chunk_id if business_ranked else "",
        "final_selected_context_ids": [str(row.get("chunk_id") or "") for row in fused_rows],
    }
    if rerank_decision.get("fallback"):
        warnings.append(str(rerank_decision.get("skip_reason") or "model_rerank_failed"))
    fused_rows = [row for row in fused_rows if is_reliable(row)]
    if include_relation_expansion:
        relation_rows = repository.approved_relation_target_rows(
            [str(row.get("document_id") or "") for row in fused_rows],
            [str(row.get("chunk_id") or "") for row in fused_rows],
            min(2, request.limit),
        )
        if relation_rows:
            fused_rows = [*fused_rows, *relation_rows]
    if not fused_rows:
        warnings.append("no_reliable_source")

    try:
        display_context_rows = repository.display_context_rows_for_results(fused_rows)
    except Exception as exc:
        logger.warning("source_parent_missing", extra={"event": "source_parent_missing", "reason": f"display_context_query_failed:{exc.__class__.__name__}"})
        warnings.append("display_context_unavailable")
        display_context_rows = {}
    enriched_rows = []
    for row in fused_rows:
        item = dict(row)
        item["display_context"] = build_display_context(item, display_context_rows.get(row_context_key(item)))
        enriched_rows.append(item)

    results = [to_result(row) for row in enriched_rows]
    ranking_debug["final_result_count"] = len(results)
    ranking_debug["final_selected_context_ids"] = [result.chunk_id for result in results]
    trace = retrieval_trace_payload(
        query_expansion=query_expansion,
        ranking_debug={
            **ranking_debug,
            "query_understanding": query_understanding.as_debug(),
        },
        warnings=warnings,
        selected_rows=enriched_rows,
    )
    latency_ms = repository.log_retrieval(
        request.query,
        retrieval_log_filters(request.filters, candidate_filters, applied_query_filters),
        request.mode,
        len(results),
        started_at,
        trace=trace,
    )
    return RetrievalResponse(
        query=request.query,
        normalized_query=normalized_query,
        query_expansion=query_expansion,
        mode=request.mode,
        results=results,
        citations=[result.citation for result in results],
        warnings=warnings,
        latency_ms=latency_ms,
        ranking_debug=ranking_debug if request.debug else {},
    )


def retrieval_trace_payload(
    *,
    query_expansion: dict[str, Any],
    ranking_debug: dict[str, Any],
    warnings: list[str],
    selected_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query_expansion": query_expansion,
        "ranking_debug": ranking_debug,
        "warnings": list(warnings),
        "selected_context": [selected_context_trace(row) for row in selected_rows],
    }


def filters_with_query_understanding(
    filters: RetrievalFilters,
    query_understanding: Any,
    ranking_mode: str,
) -> tuple[RetrievalFilters, list[str]]:
    if ranking_mode != "ai_chat" or float(getattr(query_understanding, "confidence", 0.0) or 0.0) < 0.65:
        return filters, []
    updates: dict[str, list[str]] = {}
    applied: list[str] = []
    required_scope = str(getattr(query_understanding, "required_scope", "") or "")
    if not filters.scope and required_scope not in {"", "unknown", "generic"}:
        updates["scope"] = [required_scope]
        applied.append("scope")
    required_visibility = str(getattr(query_understanding, "required_visibility", "") or "")
    if not filters.visibility and required_visibility in {"customer_facing", "internal_only"}:
        updates["visibility"] = [required_visibility]
        applied.append("visibility")
    if not updates:
        return filters, []
    return filters.model_copy(update=updates), applied


def retrieval_log_filters(input_filters: RetrievalFilters, applied_filters: RetrievalFilters, applied_query_filters: list[str]) -> dict[str, Any]:
    payload = applied_filters.model_dump()
    if applied_query_filters:
        payload["_input_filters"] = input_filters.model_dump()
        payload["_query_understanding_applied_filters"] = applied_query_filters
    return payload


def selected_context_trace(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    return {
        "chunk_id": str(row.get("chunk_id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "version_id": str(row.get("version_id") or row.get("document_version_id") or ""),
        "title": str(row.get("title") or ""),
        "heading": str(row.get("heading") or ""),
        "chunk_type": str(metadata.get("chunk_type") or metadata.get("unit_type") or row.get("section") or ""),
        "score": float(row.get("score") or 0),
        "business_score": float(row.get("business_score") or 0),
        "final_score": float(row.get("final_score") or row.get("score") or 0),
        "rank_source": list(row.get("rank_source") or []),
        "source_ref_quality": str(metadata.get("source_ref_quality") or ""),
        "source_ref_count": len(source_refs),
        "status": str(row.get("status") or metadata.get("status") or ""),
        "publish_state": str(row.get("publish_state") or metadata.get("publish_state") or ""),
        "review_status": str(row.get("review_status") or metadata.get("review_status") or ""),
        "visibility": str(row.get("visibility") or metadata.get("visibility") or ""),
        "scope": str(row.get("scope") or metadata.get("scope") or metadata.get("retrieval_scope") or ""),
        "policy_type": str(row.get("policy_type") or metadata.get("policy_type") or ""),
        "authority_level": str(row.get("authority_level") or metadata.get("authority_level") or ""),
        "score_debug": row.get("score_debug") or metadata.get("score_debug") or {},
    }


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


def keyword_candidate_rows(
    query: str,
    filters: RetrievalFilters,
    limit: int,
    debug: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if settings.meili_host:
        try:
            return meili_ai_chunk_search(query, filters, limit, debug), ""
        except Exception as exc:
            logger.warning(
                "meili_ai_chunk_search_failed",
                extra={"event": "meili_ai_chunk_search_failed", "error": exc.__class__.__name__},
            )
            return repository.lexical_search(query, filters, limit), f"meili_keyword_fallback:{exc.__class__.__name__}"
    return repository.lexical_search(query, filters, limit), "meili_keyword_unconfigured_postgres_fallback"


def meili_ai_chunk_search(query: str, filters: RetrievalFilters, limit: int, debug: bool = False) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "q": query,
        "limit": limit,
        "showRankingScore": True,
        "attributesToRetrieve": [
            "chunk_id",
            "document_id",
            "version_id",
            "title",
            "version_number",
            "status",
            "publish_state",
            "document_type",
            "review_status",
            "chunk_index",
            "section",
            "heading",
            "content",
            "metadata",
            "audience",
            "vertical",
            "category",
            "tags",
            "case_reasons",
            "visibility",
            "scope",
            "policy_type",
            "authority_level",
            "is_current_version",
        ],
    }
    if debug:
        payload["showRankingScoreDetails"] = True
    filter_text = meili_ai_chunk_filter(filters)
    if filter_text:
        payload["filter"] = filter_text
    headers = {"Content-Type": "application/json"}
    if settings.meili_master_key:
        headers["Authorization"] = f"Bearer {settings.meili_master_key}"
    with httpx.Client(timeout=2.0) as client:
        response = client.post(f"{settings.meili_host.rstrip('/')}/indexes/sop_chunks/search", json=payload, headers=headers)
        if response.status_code == 404:
            response = client.post(f"{settings.meili_host.rstrip('/')}/indexes/ai_chunks/search", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    rows = []
    for rank, hit in enumerate(data.get("hits") or [], start=1):
        if not isinstance(hit, dict):
            continue
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        row = {
            "chunk_id": str(hit.get("chunk_id") or ""),
            "document_id": str(hit.get("document_id") or ""),
            "version_id": str(hit.get("version_id") or ""),
            "title": str(hit.get("title") or ""),
            "source_filename": str(metadata.get("source_filename") or ""),
            "version_number": int(hit.get("version_number") or 0),
            "chunk_index": int(hit.get("chunk_index") or 0),
            "section": str(hit.get("section") or ""),
            "heading": str(hit.get("heading") or ""),
            "content": str(hit.get("content") or ""),
            "metadata": metadata,
            "score": float(hit.get("_rankingScore") or 0),
            "meili_score": float(hit.get("_rankingScore") or 0),
            "lexical_score": float(hit.get("_rankingScore") or 0),
            "vector_score": 0.0,
            "rank_source": ["meilisearch"],
            "best_rank": rank,
            "meili_rank": rank,
            "from_meilisearch": True,
            "status": str(hit.get("status") or ""),
            "review_status": str(hit.get("review_status") or ""),
            "publish_state": str(hit.get("publish_state") or ""),
            "category": hit.get("category") or metadata.get("category") or "",
            "vertical": hit.get("vertical") or metadata.get("vertical") or "",
            "audience": hit.get("audience") or metadata.get("audience") or [],
            "visibility": hit.get("visibility") or metadata.get("visibility") or "internal_only",
            "scope": hit.get("scope") or metadata.get("scope") or metadata.get("retrieval_scope") or "generic",
            "policy_type": hit.get("policy_type") or metadata.get("policy_type") or metadata.get("unit_type") or "",
            "authority_level": hit.get("authority_level") or metadata.get("authority_level") or "policy",
            "is_current_version": bool(hit.get("is_current_version", True)),
        }
        if debug and hit.get("_rankingScoreDetails") is not None:
            row["meili_ranking_score_details"] = hit.get("_rankingScoreDetails")
        rows.append(row)
    return rows


def meili_ai_chunk_filter(filters: RetrievalFilters) -> str:
    clauses = []
    statuses = filters.status or ["published"]
    clauses.append(or_filter("status", [str(status) for status in statuses]))
    if statuses == ["published"]:
        clauses.append('publish_state = "published_ready"')
    for field, values in [
        ("audience", filters.audience),
        ("visibility", filters.visibility),
        ("scope", filters.scope),
        ("policy_type", filters.policy_type),
        ("authority_level", filters.authority_level),
        ("vertical", filters.vertical),
        ("category", filters.category),
        ("tags", filters.tags),
        ("case_reasons", filters.case_reasons),
        ("collections", filters.collections),
        ("document_id", filters.document_ids),
    ]:
        clause = or_filter(field, values)
        if clause:
            clauses.append(clause)
    unit_clause = or_filter("unit_type", filters.unit_types)
    if unit_clause:
        clauses.append(unit_clause)
    return " AND ".join(clause for clause in clauses if clause)


def or_filter(field: str, values: list[str]) -> str:
    cleaned = [str(value).replace('"', '\\"') for value in values if str(value).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return f'{field} = "{cleaned[0]}"'
    return "(" + " OR ".join(f'{field} = "{value}"' for value in cleaned) + ")"


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
    heading = "" if is_bad_search_label(row.get("heading") or "", row.get("content") or "") else str(row.get("heading") or "")
    text = normalize_phrase(" ".join([heading, str(row.get("content") or "")]))
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
        "macro_table",
        "wording_rule",
        "sla_rule",
        "decision_rule",
        "escalation_rule",
        "case_creation_rule",
        "handoff_rule",
        "decision_point",
        "workflow_step",
        "macro_script",
        "issue_router_unit",
        "quick_action_rule",
        "sop_reference",
        "tool_link",
        "vip_overlay_rule",
        "product_update_note",
        "security_note",
        "compliance_note",
        "compliance_rule",
        "warning",
        "example",
    }
    if unit_type in action_unit_types and metadata_overlap:
        boost += 0.025
        if unit_type in {"issue_router_unit", "quick_action_rule", "tool_link"}:
            boost += 0.08

    if unit_type in action_unit_types and text_overlap:
        coverage = text_overlap / max(1, len(query_tokens))
        boost += min(0.18, coverage * 0.12)
        if unit_type == "issue_router_unit":
            boost += min(0.16, coverage * 0.14)

    if normalized_query and normalized_query in text:
        boost += 0.18

    if unit_type == "sop_reference" and metadata_overlap:
        boost += 0.04

    if has_prohibition_intent(normalized_query) and has_prohibition_answer(text):
        boost += 0.28
        if unit_type in {"security_note", "compliance_note", "compliance_rule", "warning", "operational_note", "policy_rule", "exception_rule"}:
            boost += 0.08

    if any(token in query_tokens for token in {"zt", "bao", "mat", "security", "compliance", "khong", "cam"}) and unit_type in {"security_note", "compliance_note", "compliance_rule", "warning", "operational_note"}:
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
    display_context = row.get("display_context")
    if not isinstance(display_context, DisplayContext):
        display_context = build_display_context(row, None)
    primary_highlight = display_context.highlights[0] if display_context.highlights else None
    source_anchor = display_context.source_anchor or source_anchor_for_row(row, metadata)

    citation = Citation(
        document_id=str(row["document_id"]),
        version_id=str(row["version_id"]),
        chunk_id=str(row["chunk_id"]),
        chunk_index=int(row["chunk_index"]),
        section=str(row["section"]),
        title=str(row["title"]),
        version_number=int(row["version_number"]),
        source_filename=str(row["source_filename"]),
        sop_id=str(row["document_id"]),
        document_title=display_context.document_title or str(row["title"]),
        section_id=display_context.section_id,
        section_title=display_context.section_title,
        category=display_context.category,
        collections=display_context.collections,
        highlight_start_offset=primary_highlight.start_offset if primary_highlight else None,
        highlight_end_offset=primary_highlight.end_offset if primary_highlight else None,
        chunk_text=str(row["content"]),
        source_anchor=source_anchor,
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
        sop_id=citation.document_id,
        document_title=citation.document_title,
        section_id=citation.section_id,
        section_title=citation.section_title,
        category=citation.category,
        collections=citation.collections,
        chunk_text=str(row["content"]),
        highlight_start_offset=citation.highlight_start_offset,
        highlight_end_offset=citation.highlight_end_offset,
        display_context=display_context,
        source_anchor=source_anchor,
        matched_chunk=matched_chunk_context(row, metadata),
        parent=parent_result_context(row, metadata, display_context),
        display=retrieval_display_contract(row, metadata, display_context, source_anchor),
        score_debug=row.get("score_debug") if isinstance(row.get("score_debug"), dict) else metadata.get("score_debug") if isinstance(metadata.get("score_debug"), dict) else {},
    )


def row_context_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("document_id") or ""), str(row.get("version_id") or ""))


def matched_chunk_context(row: dict[str, Any], metadata: dict[str, Any]) -> MatchedChunkContext:
    refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    return MatchedChunkContext(
        chunk_id=str(row.get("chunk_id") or ""),
        title=str(row.get("heading") or row.get("title") or ""),
        snippet=str(row.get("content") or ""),
        chunk_type=str(metadata.get("chunk_type") or metadata.get("unit_type") or row.get("section") or ""),
        score=round(float(row.get("score") or 0), 8),
        source_refs=[ref for ref in refs if isinstance(ref, dict)],
    )


def parent_result_context(row: dict[str, Any], metadata: dict[str, Any], display_context: DisplayContext) -> ParentResultContext:
    section_path = metadata.get("section_path") if isinstance(metadata.get("section_path"), list) else []
    return ParentResultContext(
        parent_section_id=str(metadata.get("parent_section_id") or display_context.section_id or metadata.get("section_id") or ""),
        parent_chunk_id=str(metadata.get("parent_chunk_id") or metadata.get("parent_unit_id") or ""),
        title=display_context.section_title or first_text(metadata.get("section_title"), row.get("heading"), row.get("section")),
        section_path=[str(item) for item in section_path if str(item).strip()],
        markdown=display_context.content if display_context.source_resolution_status == "resolved" else "",
    )


def retrieval_display_contract(
    row: dict[str, Any],
    metadata: dict[str, Any],
    display_context: DisplayContext,
    source_anchor: SourceAnchor,
) -> RetrievalDisplayContract:
    refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    first_ref = next((ref for ref in refs if isinstance(ref, dict)), {})
    open_mode = "workflow_diagram" if is_workflow_diagram_result(row, metadata) else "full_document"
    return RetrievalDisplayContract(
        open_mode=open_mode,
        highlight_source_refs=[ref for ref in refs if isinstance(ref, dict)],
        scroll_target=ScrollTarget(
            block_id=source_anchor.block_id,
            paragraph_index=first_int(first_ref.get("paragraph_index")),
            table_index=first_int(first_ref.get("table_index")),
            row_index=source_anchor.row_index,
        ),
    )


def build_display_context(row: dict[str, Any], context: dict[str, Any] | None) -> DisplayContext:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    document_metadata = context.get("document_metadata") if context and isinstance(context.get("document_metadata"), dict) else {}
    chunks = context.get("chunks") if context and isinstance(context.get("chunks"), list) else []
    source_chunk_id = str(row.get("chunk_id") or "")
    source_text = str(row.get("content") or "")
    source_section = str(row.get("section") or "")
    source_heading = str(row.get("heading") or "")
    document_title = str((context or {}).get("document_title") or row.get("title") or "")
    version_number = int((context or {}).get("version_number") or row.get("version_number") or 0)
    source_anchor = source_anchor_for_row(row, metadata)

    if is_workflow_diagram_result(row, metadata, document_metadata):
        return workflow_diagram_display_context(row, metadata, context, document_metadata, source_anchor)

    if not context:
        log_source_resolution("source_parent_missing", row, source_anchor, "display_context_not_loaded")
        return missing_source_context(row, metadata, source_anchor, "parent_missing", "display_context_not_loaded")

    context_version_id = str(context.get("version_id") or "")
    if context_version_id and context_version_id != str(row.get("version_id") or ""):
        log_source_resolution("source_version_mismatch", row, source_anchor, f"{row.get('version_id')}!={context_version_id}")
        return missing_source_context(row, metadata, source_anchor, "version_mismatch", "retrieval_version_does_not_match_display_context")

    is_table_row = is_table_row_chunk(row)
    resolved_table_row = False
    if is_table_row:
        table_chunks = matching_table_chunks(chunks, source_anchor)
        if table_chunks:
            display_unit_type = "table_section"
            blocks = [block_from_chunk(chunk) for chunk in table_chunks]
            display_content = "\n".join(block_text(chunk) for chunk in table_chunks).strip()
            highlight = DisplayHighlight(
                chunk_id=source_chunk_id,
                text=source_text,
                match_strategy="table_row_anchor",
                source_anchor=source_anchor,
            )
            resolved_table_row = True
        else:
            log_source_resolution("source_parent_missing", row, source_anchor, "table_parent_not_found")
            return missing_source_context(row, metadata, source_anchor, "parent_missing", "table_parent_not_found")

    source_chunks = [chunk for chunk in chunks if is_source_evidence_chunk(chunk)]
    source_match = None if is_table_row else matching_source_section(source_chunks, source_chunk_id, source_text)
    if resolved_table_row:
        pass
    elif source_match:
        source_chunk, highlight = source_match
        display_unit_type = "source_section"
        display_content = str(source_chunk.get("content") or "")
        blocks = [block_from_chunk(source_chunk)]
        source_heading = str(source_chunk.get("heading") or source_heading)
    else:
        section_chunks = [
            chunk for chunk in chunks
            if section_id_for_chunk(chunk) == source_anchor.section_id
            and not is_source_evidence_chunk(chunk)
            and not is_document_layer_chunk(chunk)
        ]
        if section_chunks:
            display_unit_type = "section"
            display_content = "\n\n".join(block_text(chunk) for chunk in section_chunks).strip()
            blocks = [block_from_chunk(chunk) for chunk in section_chunks]
            highlight = display_highlight(source_chunk_id, source_text, display_content, source_anchor)
        elif source_chunks:
            display_unit_type = "source_document"
            display_content = "\n\n".join(block_text(chunk) for chunk in source_chunks).strip()
            blocks = [block_from_chunk(chunk) for chunk in source_chunks]
            highlight = display_highlight(source_chunk_id, source_text, display_content, source_anchor)
        else:
            log_source_resolution("source_parent_missing", row, source_anchor, "section_parent_not_found")
            return missing_source_context(row, metadata, source_anchor, "parent_missing", "section_parent_not_found")

    collections = collection_refs(metadata, document_metadata)
    category = first_text(metadata.get("category"), document_metadata.get("category"))
    highlight_failed = highlight.start_offset is None and highlight.end_offset is None and highlight.match_strategy != "table_row_anchor"
    log_source_resolution("source_highlight_failed" if highlight_failed else "source_highlight_success", row, source_anchor, highlight.match_strategy)

    return DisplayContext(
        display_unit_type=display_unit_type,
        document_id=str(row.get("document_id") or ""),
        document_title=document_title,
        section_id=source_anchor.section_id,
        section_title=source_heading or source_section,
        category=category,
        collections=collections,
        version_number=version_number or None,
        last_updated=(context or {}).get("updated_at"),
        published_at=(context or {}).get("published_at"),
        effective_date=first_text(metadata.get("effective_from"), metadata.get("effective_date"), document_metadata.get("effective_from")),
        content=display_content,
        blocks=blocks,
        highlights=[highlight],
        fallback_excerpt=source_text if highlight_failed else "",
        highlight_failed=highlight_failed,
        source_anchor=source_anchor,
        source_resolution_status="resolved",
    )


def is_workflow_diagram_result(
    row: dict[str, Any],
    metadata: dict[str, Any],
    document_metadata: dict[str, Any] | None = None,
) -> bool:
    document_metadata = document_metadata if isinstance(document_metadata, dict) else {}
    unit_type = str(metadata.get("unit_type") or row.get("section") or "")
    workflow_types = {
        "full_workflow_diagram",
        "workflow_phase",
        "workflow_step",
        "decision_node",
        "decision_branch",
        "workflow_path",
        "script_block",
        "annotation",
        "relation_to_sop",
        "visual_source_block",
    }
    return (
        metadata.get("open_mode") == "workflow_diagram"
        or metadata.get("display_unit_type") == "workflow_diagram"
        or metadata.get("document_type") == "workflow_diagram"
        or document_metadata.get("document_type") == "workflow_diagram"
        or unit_type in workflow_types
    )


def workflow_diagram_display_context(
    row: dict[str, Any],
    metadata: dict[str, Any],
    context: dict[str, Any] | None,
    document_metadata: dict[str, Any],
    source_anchor: SourceAnchor,
) -> DisplayContext:
    source_text = str(metadata.get("display_text") or metadata.get("source_text") or row.get("content") or "")
    source_chunk_id = str(row.get("chunk_id") or "")
    refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    has_bbox = any(isinstance(ref, dict) and isinstance(ref.get("bbox"), list) and len(ref.get("bbox") or []) >= 4 for ref in refs)
    unit_type = str(metadata.get("unit_type") or row.get("section") or "")
    phase = first_text(metadata.get("phase"))
    lane = first_text(metadata.get("lane"), metadata.get("actor"))
    step_code = first_text(metadata.get("step_code"), metadata.get("from_step_code"))
    section_title = first_text(
        metadata.get("section_title"),
        " / ".join(part for part in [phase, lane, f"Step {step_code}" if step_code else ""] if part),
        row.get("heading"),
        row.get("section"),
    )
    document_title = str((context or {}).get("document_title") or metadata.get("document_title") or row.get("title") or "")
    document_id = str(row.get("document_id") or "")
    version_number = int((context or {}).get("version_number") or row.get("version_number") or 0) or None
    collections = collection_refs(metadata, document_metadata)
    category = first_text(metadata.get("category"), document_metadata.get("category"))
    highlight = DisplayHighlight(
        chunk_id=source_chunk_id,
        text=source_text,
        match_strategy="visual_bbox" if has_bbox else "workflow_source_ref",
        source_anchor=source_anchor,
    )
    block = DisplayBlock(
        id=source_anchor.block_id or source_chunk_id,
        title=str(row.get("heading") or section_title or unit_type),
        content=source_text,
        unit_type=unit_type,
        chunk_id=source_chunk_id,
        block_type="workflow_diagram",
        source_anchor=source_anchor,
    )
    log_source_resolution("source_highlight_success", row, source_anchor, highlight.match_strategy)
    return DisplayContext(
        display_unit_type="workflow_diagram",
        document_id=document_id,
        document_title=document_title,
        section_id=source_anchor.section_id,
        section_title=section_title,
        category=category,
        collections=collections,
        version_number=version_number,
        last_updated=(context or {}).get("updated_at"),
        published_at=(context or {}).get("published_at"),
        effective_date=first_text(metadata.get("effective_from"), metadata.get("effective_date"), document_metadata.get("effective_from")),
        content=source_text,
        blocks=[block],
        highlights=[highlight],
        fallback_excerpt="",
        highlight_failed=False,
        source_anchor=source_anchor,
        source_resolution_status="resolved",
    )


def matching_source_section(source_chunks: list[dict[str, Any]], chunk_id: str, chunk_text: str) -> tuple[dict[str, Any], DisplayHighlight] | None:
    for source_chunk in source_chunks:
        highlight = display_highlight(chunk_id, chunk_text, str(source_chunk.get("content") or ""), source_anchor_for_row(source_chunk))
        if highlight.start_offset is not None and highlight.end_offset is not None:
            return source_chunk, highlight
    return None


def missing_source_context(row: dict[str, Any], metadata: dict[str, Any], source_anchor: SourceAnchor, status: str, reason: str) -> DisplayContext:
    return DisplayContext(
        display_unit_type="missing_source",
        document_id=str(row.get("document_id") or ""),
        document_title=str(row.get("title") or ""),
        section_id=source_anchor.section_id,
        section_title=first_text(metadata.get("section_title"), row.get("heading"), row.get("section")),
        category=first_text(metadata.get("category")),
        version_number=int(row.get("version_number") or 0) or None,
        content="Source section could not be loaded for this published result.",
        blocks=[],
        highlights=[],
        fallback_excerpt="",
        highlight_failed=True,
        source_anchor=source_anchor,
        source_resolution_status=status,
        source_resolution_reason=reason,
    )


def log_source_resolution(event: str, row: dict[str, Any], source_anchor: SourceAnchor, reason: str) -> None:
    payload = {
        "event": event,
        "chunk_id": str(row.get("chunk_id") or ""),
        "sop_id": source_anchor.sop_id,
        "sop_version_id": source_anchor.sop_version_id,
        "section_id": source_anchor.section_id,
        "table_id": source_anchor.table_id,
        "row_index": source_anchor.row_index,
        "reason": reason,
    }
    if event in {"source_highlight_failed", "source_parent_missing", "source_version_mismatch", "source_permission_denied"}:
        logger.warning(event, extra=payload)
    else:
        logger.info(event, extra=payload)


def is_document_layer_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    unit_type = str(metadata.get("unit_type") or chunk.get("section") or "")
    scope = str(metadata.get("retrieval_scope") or "")
    return scope == "document" or unit_type == "full_sop"


def is_source_evidence_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    unit_type = str(metadata.get("unit_type") or chunk.get("section") or "")
    scope = str(metadata.get("retrieval_scope") or "")
    return scope == "source_evidence" or unit_type == "source_evidence_section" or metadata.get("source_evidence_only") is True


def block_from_chunk(chunk: dict[str, Any]) -> DisplayBlock:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    return DisplayBlock(
        id=str(chunk.get("chunk_id") or chunk.get("id") or ""),
        title=str(chunk.get("heading") or ""),
        content=str(chunk.get("content") or ""),
        unit_type=str(metadata.get("unit_type") or chunk.get("section") or ""),
        chunk_id=str(chunk.get("chunk_id") or chunk.get("id") or ""),
        block_type=block_type_for_chunk(chunk),
        source_anchor=source_anchor_for_row(chunk),
    )


def block_text(chunk: dict[str, Any]) -> str:
    heading = str(chunk.get("heading") or "").strip()
    content = str(chunk.get("content") or "").strip()
    return f"{heading}\n{content}".strip() if heading and heading not in content[:160] else content


def display_highlight(chunk_id: str, chunk_text: str, display_content: str, source_anchor: SourceAnchor | None = None) -> DisplayHighlight:
    anchor = source_anchor or SourceAnchor()
    if not chunk_text or not display_content:
        return DisplayHighlight(chunk_id=chunk_id, text=chunk_text, match_strategy="unmatched", source_anchor=anchor)

    exact_start = display_content.find(chunk_text)
    if exact_start >= 0:
        return DisplayHighlight(
            chunk_id=chunk_id,
            text=chunk_text,
            start_offset=exact_start,
            end_offset=exact_start + len(chunk_text),
            match_strategy="exact",
            source_anchor=anchor,
        )

    normalized_range = normalized_match_range(display_content, chunk_text)
    if normalized_range:
        return DisplayHighlight(
            chunk_id=chunk_id,
            text=chunk_text,
            start_offset=normalized_range[0],
            end_offset=normalized_range[1],
            match_strategy="normalized",
            source_anchor=anchor,
        )

    paragraph_range = paragraph_match_range(display_content, chunk_text)
    if paragraph_range:
        return DisplayHighlight(
            chunk_id=chunk_id,
            text=chunk_text,
            start_offset=paragraph_range[0],
            end_offset=paragraph_range[1],
            match_strategy="paragraph",
            source_anchor=anchor,
        )

    return DisplayHighlight(chunk_id=chunk_id, text=chunk_text, match_strategy="unmatched", source_anchor=anchor)


def normalized_match_range(haystack: str, needle: str) -> tuple[int, int] | None:
    normalized_haystack, haystack_map = normalized_match_text(haystack)
    normalized_needle, _needle_map = normalized_match_text(needle)
    normalized_needle = normalized_needle.strip()
    if not normalized_haystack or not normalized_needle:
        return None
    start = normalized_haystack.find(normalized_needle)
    if start < 0:
        return None
    end = start + len(normalized_needle)
    mapped_start = haystack_map[start]
    mapped_end = haystack_map[end - 1] + 1
    return mapped_start, mapped_end


def normalized_match_text(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    mapping: list[int] = []
    last_space = False
    for index, char in enumerate(value):
        normalized = unicodedata.normalize("NFKD", char)
        normalized = "".join(item for item in normalized if not unicodedata.combining(item)).replace("đ", "d").replace("Đ", "D").lower()
        if re.match(r"[a-z0-9]", normalized):
            chars.append(normalized)
            mapping.append(index)
            last_space = False
        elif char.isspace() or not re.match(r"[a-z0-9]", normalized):
            if not last_space and chars:
                chars.append(" ")
                mapping.append(index)
                last_space = True
    if chars and chars[-1] == " ":
        chars.pop()
        mapping.pop()
    return "".join(chars), mapping


def paragraph_match_range(haystack: str, needle: str) -> tuple[int, int] | None:
    target_tokens = {token for token in normalized_match_text(needle)[0].split(" ") if len(token) > 2}
    if not target_tokens:
        return None
    best: tuple[int, int, int] | None = None
    for start, end in paragraph_ranges(haystack):
        paragraph_tokens = set(normalized_match_text(haystack[start:end])[0].split(" "))
        score = len(target_tokens.intersection(paragraph_tokens))
        if best is None or score > best[2]:
            best = (start, end, score)
    threshold = min(5, max(2, (len(target_tokens) + 1) // 2))
    if best and best[2] >= threshold:
        return best[0], best[1]
    return None


def paragraph_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"\n\s*\n", value):
        end = match.start()
        if value[start:end].strip():
            ranges.append(trim_range(value, start, end))
        start = match.end()
    if value[start:].strip():
        ranges.append(trim_range(value, start, len(value)))
    return ranges or [(0, len(value))]


def trim_range(value: str, start: int, end: int) -> tuple[int, int]:
    while start < end and value[start].isspace():
        start += 1
    while end > start and value[end - 1].isspace():
        end -= 1
    return start, end


def source_anchor_for_row(row: dict[str, Any], metadata: dict[str, Any] | None = None) -> SourceAnchor:
    item_metadata = metadata if isinstance(metadata, dict) else row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_refs = item_metadata.get("source_refs") if isinstance(item_metadata.get("source_refs"), list) else []
    source_ref = next((ref for ref in source_refs if isinstance(ref, dict)), {})
    table_index = first_text(
        item_metadata.get("table_id"),
        item_metadata.get("source_table_id"),
        item_metadata.get("source_table_index"),
        item_metadata.get("table_index"),
        source_ref.get("table_id"),
        source_ref.get("table_index"),
        source_ref.get("sheet"),
    )
    row_index = first_int(
        item_metadata.get("row_index"),
        item_metadata.get("source_row_index"),
        item_metadata.get("row_number"),
        source_ref.get("row_index"),
        source_ref.get("row_start"),
    )
    section_title = first_text(
        item_metadata.get("section_title"),
        last_text(item_metadata.get("section_path")),
        last_text(source_ref.get("heading_path")),
        row.get("heading"),
        row.get("section"),
    )
    section_id = first_text(
        item_metadata.get("section_id"),
        item_metadata.get("source_section_id"),
        source_ref.get("section_id"),
        stable_section_id(last_text(item_metadata.get("section_path"))),
        stable_section_id(last_text(source_ref.get("heading_path"))),
        row.get("section"),
        stable_section_id(section_title),
        row.get("chunk_id"),
    )
    table_id = ""
    if table_index:
        table_id = str(table_index)
        if table_id.isdigit():
            table_id = f"table_{table_id}"
        elif source_ref.get("sheet"):
            table_id = f"sheet_{stable_section_id(table_id)}"
    block_id = first_text(
        item_metadata.get("block_id"),
        source_ref.get("block_id"),
        f"{table_id}_row_{row_index}" if table_id and row_index is not None else "",
        f"{section_id}_block",
    )
    column_key = first_text(
        item_metadata.get("column_key"),
        item_metadata.get("source_column_key"),
        first_column(source_ref.get("column_names")),
    )
    return SourceAnchor(
        sop_id=str(row.get("document_id") or item_metadata.get("sop_id") or ""),
        sop_version_id=str(row.get("version_id") or item_metadata.get("sop_version_id") or ""),
        section_id=section_id,
        block_id=block_id,
        table_id=table_id,
        row_index=row_index,
        column_key=column_key,
    )


def is_table_row_chunk(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    unit_type = str(metadata.get("unit_type") or row.get("section") or "")
    source_ref_quality = str(metadata.get("source_ref_quality") or "")
    source_refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    has_table_ref = any(
        isinstance(ref, dict)
        and (
            (ref.get("table_index") is not None and ref.get("row_index") is not None)
            or (ref.get("sheet") and (ref.get("row_start") is not None or ref.get("row_end") is not None))
        )
        for ref in source_refs
    )
    return (
        unit_type in {"table_row", "rule_table_row", "candidate_table_row"}
        or source_ref_quality in {"table_row", "sheet_row"}
        or metadata.get("source_row_index") is not None
        or metadata.get("row_number") is not None
        or has_table_ref
    )


def matching_table_chunks(chunks: list[dict[str, Any]], source_anchor: SourceAnchor) -> list[dict[str, Any]]:
    if not source_anchor.table_id:
        return []
    matching = [
        chunk for chunk in chunks
        if not is_document_layer_chunk(chunk)
        and not is_source_evidence_chunk(chunk)
        and source_anchor_for_row(chunk).table_id == source_anchor.table_id
    ]
    matching.sort(key=lambda chunk: source_anchor_for_row(chunk).row_index or int(chunk.get("chunk_index") or 0))
    return matching


def section_id_for_chunk(chunk: dict[str, Any]) -> str:
    return source_anchor_for_row(chunk).section_id


def block_type_for_chunk(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    if is_table_row_chunk(chunk):
        return "table_row"
    if metadata.get("block_type"):
        return str(metadata.get("block_type"))
    if metadata.get("retrieval_scope") == "source_evidence":
        return "source_section"
    return "paragraph"


def collection_refs(metadata: dict[str, Any], document_metadata: dict[str, Any]) -> list[CollectionRef]:
    values: list[CollectionRef] = []
    for source in (metadata, document_metadata):
        slug = first_text(source.get("collection_slug"), source.get("collection"))
        name = first_text(source.get("collection_name"), slug)
        if slug or name:
            ref = CollectionRef(id=slug or name, name=name or slug)
            if ref.id and all(existing.id != ref.id for existing in values):
                values.append(ref)
    return values


def section_id_for_row(row: dict[str, Any], metadata: dict[str, Any]) -> str:
    return first_text(metadata.get("section_id"), metadata.get("source_section_id"), row.get("section"), row.get("chunk_id"))


def stable_section_id(value: Any) -> str:
    text = str(value or "").strip()
    normalized = normalized_match_text(text)[0].replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "", normalized).strip("_")
    return normalized[:80]


def first_int(*values: Any) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def last_text(value: Any) -> str:
    if isinstance(value, list):
        for item in reversed(value):
            text = str(item or "").strip()
            if text:
                return text
    return ""


def first_column(value: Any) -> str:
    if isinstance(value, list):
        return first_text(*value)
    return ""


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            value = next((item for item in value if str(item or "").strip()), "")
        text = str(value or "").strip()
        if text:
            return text
    return ""


def is_reliable(row: dict[str, Any]) -> bool:
    lexical_score = float(row.get("lexical_score") or 0)
    vector_score = float(row.get("vector_score") or 0)
    rank_sources = row.get("rank_source") or []
    if lexical_score > 0:
        return True
    if "vector" in rank_sources and vector_score >= 0.12:
        return True
    return False
