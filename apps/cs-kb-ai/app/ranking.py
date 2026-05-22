from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger("cs_kb_ai.ranking")
VALID_INTENTS = {
    "macro",
    "forbidden_wording",
    "wording",
    "compliance",
    "handling",
    "document_title",
    "generic",
}
RRF_K = 60


@dataclass(frozen=True)
class IntentMatch:
    intent: str = "generic"
    confidence: float = 0.0
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryUnderstanding:
    intent: str = "generic"
    confidence: float = 0.0
    rewritten_query: str = ""
    key_concepts: tuple[str, ...] = ()
    must_have_terms: tuple[str, ...] = ()
    preferred_chunk_types: tuple[str, ...] = ()
    risk_sensitive: bool = False
    source: str = "seed"
    warnings: tuple[str, ...] = ()

    def as_debug(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "rewritten_query": self.rewritten_query,
            "key_concepts": list(self.key_concepts),
            "must_have_terms": list(self.must_have_terms),
            "preferred_chunk_types": list(self.preferred_chunk_types),
            "risk_sensitive": self.risk_sensitive,
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass
class RankingOptions:
    mode: str = "portal_search"
    debug: bool = False
    query_understanding: QueryUnderstanding | None = None
    force_model_rerank: bool | None = None


@dataclass
class SearchCandidate:
    chunk_id: str
    document_id: str = ""
    document_version_id: str = ""
    parent_section_id: str = ""
    parent_chunk_id: str = ""
    parent_unit_id: str = ""
    title: str = ""
    normalized_title: str = ""
    content: str = ""
    retrieval_text: str = ""
    display_text: str = ""
    section_path: tuple[str, ...] = ()
    chunk_type: str = ""
    status: str = "published"
    review_status: str = ""
    risk_level: str = "low"
    source_ref_quality: str = "none"
    source_refs: tuple[dict[str, Any], ...] = ()
    category: str = ""
    collections: tuple[str, ...] = ()
    audience: tuple[str, ...] = ()
    vertical: str = ""
    updated_at: str = ""
    effective_from: str = ""
    is_current_version: bool = True
    macro_text: str = ""
    forbidden_phrases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    meili_score: float = 0.0
    vector_score: float = 0.0
    lexical_score: float = 0.0
    fusion_score: float = 0.0
    business_score: float = 0.0
    model_rerank_score: float | None = None
    final_score: float = 0.0
    from_meilisearch: bool = False
    from_vector: bool = False
    meili_rank: int | None = None
    vector_rank: int | None = None
    score_debug: dict[str, Any] = field(default_factory=dict)
    raw_row: dict[str, Any] = field(default_factory=dict)

    def text_for_rerank(self, max_chars: int = 1400) -> str:
        section = " > ".join(self.section_path)
        parts = [
            f"Title: {self.title}",
            f"Section: {section}" if section else "",
            f"Type: {self.chunk_type}",
            f"Content: {(self.retrieval_text or self.content)[:max_chars]}",
        ]
        return "\n".join(part for part in parts if part)


_CONFIG_CACHE: dict[str, Any] | None = None
_QUERY_UNDERSTANDING_CACHE: dict[str, tuple[float, QueryUnderstanding]] = {}
_RERANK_CACHE: dict[str, tuple[float, dict[str, float]]] = {}


def load_ranking_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    path = Path(settings.ranking_config_path) if settings.ranking_config_path else default_config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _CONFIG_CACHE = validate_ranking_config(payload)
        return _CONFIG_CACHE
    except Exception as exc:
        logger.warning("ranking_config_load_failed", extra={"event": "ranking_config_load_failed", "path": str(path), "error": exc.__class__.__name__})
        _CONFIG_CACHE = validate_ranking_config(default_ranking_config())
        return _CONFIG_CACHE


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "ranking" / "sop_ranking.yml"


def validate_ranking_config(payload: dict[str, Any]) -> dict[str, Any]:
    base = default_ranking_config()
    merged = deep_merge(base, payload if isinstance(payload, dict) else {})
    for key in ("modes", "stable_boosts", "chunk_type_priorities", "intent_rules"):
        if not isinstance(merged.get(key), dict):
            merged[key] = base[key]
    if int(merged.get("version") or 0) <= 0:
        merged["version"] = 1
    return merged


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    output = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(output.get(key), dict):
            output[key] = deep_merge(output[key], value)
        else:
            output[key] = value
    return output


def default_ranking_config() -> dict[str, Any]:
    return {
        "version": 1,
        "modes": {
            "portal_search": {"candidate_limit": 50, "output_limit": 10, "model_rerank_enabled": False},
            "admin_search": {"candidate_limit": 80, "output_limit": 20, "model_rerank_enabled": False},
            "ai_chat": {
                "keyword_candidate_limit": 30,
                "vector_candidate_limit": 30,
                "merged_candidate_limit": 40,
                "business_rerank_limit": 20,
                "model_rerank_enabled": True,
                "model_rerank_limit": 15,
                "output_context_limit": 8,
            },
        },
        "stable_boosts": {
            "meili_score_weight": 100,
            "vector_score_weight": 100,
            "fusion_bonus": 8,
            "rrf_weight": 100,
            "grouped_context_for_intent": 14,
            "strong_exact_phrase_threshold": 22,
            "strong_top_gap": 18,
            "exact_phrase": {
                "title": 18,
                "normalized_title": 18,
                "section_path": 10,
                "macro_text": 16,
                "forbidden_phrases": 20,
                "content": 12,
                "max_total": 30,
            },
            "source_ref_quality": {"table_row": 8, "block_id": 6, "paragraph_only": 3, "none": -20},
            "status": {"published": 15, "approved": 5, "needs_review": -20, "draft": -40},
            "current_version": {"true": 8, "false": -25},
            "risk_for_compliance": {"critical": 10, "high": 7, "medium": 3, "low": 0},
            "stale_version_penalty": -25,
            "duplicate_parent_penalty": {"second": -8, "third_or_more": -16},
            "example_penalty_when_policy_exists": -8,
            "full_sop_penalty_for_specific_query": -10,
        },
        "chunk_type_priorities": {"generic": {"source_evidence_section": 4}},
        "intent_rules": {},
        "model_query_understanding": {
            "enabled_for_ai_chat": True,
            "enabled_for_portal": False,
            "cache_ttl_seconds": 86400,
        },
        "model_rerank_gate": {
            "minimum_candidates": 3,
            "maximum_total_candidate_chars": 22000,
            "semantic_query_min_words": 5,
        },
    }


def mode_config(config: dict[str, Any], mode: str) -> dict[str, Any]:
    modes = config.get("modes") if isinstance(config.get("modes"), dict) else {}
    selected = modes.get(mode) if isinstance(modes.get(mode), dict) else {}
    return selected


def seed_intent(query: str, config: dict[str, Any] | None = None) -> IntentMatch:
    config = config or load_ranking_config()
    normalized_query = normalize_text(query)
    rules = config.get("intent_rules") if isinstance(config.get("intent_rules"), dict) else {}
    best = IntentMatch()
    for intent, rule in rules.items():
        if intent not in VALID_INTENTS or not isinstance(rule, dict):
            continue
        seed_terms = [str(term) for term in rule.get("seed_terms") or [] if str(term).strip()]
        matched = tuple(term for term in seed_terms if normalize_text(term) in normalized_query)
        if not matched:
            continue
        confidence = min(0.95, 0.55 + 0.15 * len(matched))
        if len(matched) > len(best.matched_terms) or (len(matched) == len(best.matched_terms) and confidence > best.confidence):
            best = IntentMatch(intent=intent, confidence=confidence, matched_terms=matched)
    return best


def understand_query(query: str, mode: str, config: dict[str, Any] | None = None) -> QueryUnderstanding:
    config = config or load_ranking_config()
    seed = seed_intent(query, config)
    fallback = QueryUnderstanding(intent=seed.intent, confidence=seed.confidence, key_concepts=seed.matched_terms, source="seed")
    model_cfg = config.get("model_query_understanding") if isinstance(config.get("model_query_understanding"), dict) else {}
    if mode != "ai_chat" or not bool(model_cfg.get("enabled_for_ai_chat", False)):
        return fallback
    if not settings.openrouter_api_key:
        return replace(fallback, warnings=("query_understanding_model_disabled",))
    ttl = int(model_cfg.get("cache_ttl_seconds") or 86400)
    cache_key = stable_hash({"query": query, "config_version": config.get("version"), "model": settings.openrouter_chat_simple_model})
    cached = _QUERY_UNDERSTANDING_CACHE.get(cache_key)
    now = time.time()
    if cached and cached[0] > now:
        logger.info("query_understanding_cache_hit", extra={"event": "query_understanding_cache_hit", "mode": mode})
        return cached[1]
    logger.info("query_understanding_cache_miss", extra={"event": "query_understanding_cache_miss", "mode": mode})
    try:
        payload = {
            "model": settings.openrouter_chat_simple_model or settings.openrouter_chat_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are analyzing a Vietnamese customer support SOP search query. "
                        "Do not answer the query. Return only JSON. Classify retrieval intent and extract key concepts. "
                        "Avoid adding policy facts not present in the query."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Query:\n"
                        f"{query}\n\n"
                        "Return JSON: {\"intent\":\"macro|forbidden_wording|wording|compliance|handling|document_title|generic\","
                        "\"confidence\":0.0,\"rewritten_query\":\"string\",\"key_concepts\":[\"string\"],"
                        "\"must_have_terms\":[\"string\"],\"preferred_chunk_types\":[\"string\"],\"risk_sensitive\":true}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        data = openrouter_chat_json(payload, timeout_seconds=min(settings.openrouter_timeout_seconds, 4))
        understood = normalize_query_understanding(data, fallback)
        _QUERY_UNDERSTANDING_CACHE[cache_key] = (now + ttl, understood)
        return understood
    except Exception as exc:
        logger.warning("query_understanding_failed", extra={"event": "query_understanding_failed", "error": exc.__class__.__name__})
        return replace(fallback, warnings=(*fallback.warnings, f"query_understanding_failed:{exc.__class__.__name__}"))


def normalize_query_understanding(payload: Any, fallback: QueryUnderstanding) -> QueryUnderstanding:
    if not isinstance(payload, dict):
        return replace(fallback, warnings=(*fallback.warnings, "query_understanding_invalid_shape"))
    intent = str(payload.get("intent") or fallback.intent).strip()
    if intent not in VALID_INTENTS:
        intent = fallback.intent
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = fallback.confidence
    confidence = max(0.0, min(1.0, confidence))
    if confidence < 0.2:
        intent = fallback.intent
    return QueryUnderstanding(
        intent=intent,
        confidence=confidence,
        rewritten_query=str(payload.get("rewritten_query") or ""),
        key_concepts=string_tuple(payload.get("key_concepts")),
        must_have_terms=string_tuple(payload.get("must_have_terms")),
        preferred_chunk_types=string_tuple(payload.get("preferred_chunk_types")),
        risk_sensitive=bool(payload.get("risk_sensitive")),
        source="model",
        warnings=fallback.warnings,
    )


def business_rerank(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions | None = None,
    config: dict[str, Any] | None = None,
) -> list[SearchCandidate]:
    options = options or RankingOptions()
    config = config or load_ranking_config()
    candidates = filter_candidates_for_mode(candidates, options.mode)
    seed = seed_intent(query, config)
    query_understanding = options.query_understanding or QueryUnderstanding(
        intent=seed.intent,
        confidence=seed.confidence,
        key_concepts=seed.matched_terms,
        source="seed",
    )
    scored = [
        score_candidate(query, candidate, query_understanding, options, config, any_policy_candidate(candidates))
        for candidate in candidates
    ]
    preliminary = sorted(scored, key=candidate_sort_key, reverse=True)
    with_duplicates = apply_duplicate_parent_penalties(preliminary, config, options.debug)
    return sorted(with_duplicates, key=candidate_sort_key, reverse=True)


def filter_candidates_for_mode(candidates: list[SearchCandidate], mode: str) -> list[SearchCandidate]:
    if mode != "portal_search":
        return candidates
    output = []
    for candidate in candidates:
        if normalize_key(candidate.status) != "published":
            continue
        if normalize_key(candidate.review_status) in {"draft", "needs_review", "rejected"}:
            continue
        output.append(candidate)
    return output


def score_candidate(
    query: str,
    candidate: SearchCandidate,
    query_understanding: QueryUnderstanding,
    options: RankingOptions,
    config: dict[str, Any],
    policy_exists: bool,
) -> SearchCandidate:
    stable = config.get("stable_boosts") if isinstance(config.get("stable_boosts"), dict) else {}
    boosts: dict[str, float] = {}
    penalties: dict[str, float] = {}

    meili_component = candidate.meili_score * float(stable.get("meili_score_weight") or 100)
    vector_component = candidate.vector_score * float(stable.get("vector_score_weight") or 100)
    fusion_component = candidate.fusion_score
    score = meili_component + vector_component + fusion_component
    if meili_component:
        boosts["meili_score"] = round(meili_component, 4)
    if vector_component:
        boosts["vector_score"] = round(vector_component, 4)
    if fusion_component:
        boosts["fusion_score"] = round(fusion_component, 4)

    exact_boost, exact_debug = exact_phrase_boost(query, candidate, stable, query_understanding.key_concepts)
    score += exact_boost
    if exact_boost:
        boosts["exact_phrase"] = round(exact_boost, 4)

    chunk_priority = chunk_type_priority(candidate, query_understanding.intent, config)
    if candidate.chunk_type.endswith("_group") and query_understanding.intent in {"wording", "handling", "compliance", "forbidden_wording"}:
        group_boost = float(stable.get("grouped_context_for_intent") or 0)
        chunk_priority += group_boost
    score += chunk_priority
    if chunk_priority >= 0:
        boosts["chunk_type_priority"] = round(chunk_priority, 4)
    else:
        penalties["chunk_type_priority"] = round(chunk_priority, 4)

    source_ref_boost = map_weight(stable.get("source_ref_quality"), candidate.source_ref_quality)
    score += source_ref_boost
    if source_ref_boost >= 0:
        boosts["source_ref_quality"] = round(source_ref_boost, 4)
    else:
        penalties["source_ref_quality"] = round(source_ref_boost, 4)

    status_boost = status_weight(candidate, stable)
    score += status_boost
    if status_boost >= 0:
        boosts["status"] = round(status_boost, 4)
    else:
        penalties["status"] = round(status_boost, 4)

    current_boost = map_weight(stable.get("current_version"), "true" if candidate.is_current_version else "false")
    score += current_boost
    if current_boost >= 0:
        boosts["current_version"] = round(current_boost, 4)
    else:
        penalties["current_version"] = round(current_boost, 4)
    if not candidate.is_current_version:
        stale_penalty = float(stable.get("stale_version_penalty") or 0)
        score += stale_penalty
        penalties["stale_version"] = round(stale_penalty, 4)

    if query_understanding.intent in {"compliance", "forbidden_wording"} or query_understanding.risk_sensitive:
        risk_boost = map_weight(stable.get("risk_for_compliance"), candidate.risk_level)
        score += risk_boost
        if risk_boost:
            boosts["risk_for_compliance"] = round(risk_boost, 4)

    if policy_exists and is_example(candidate):
        example_penalty = float(stable.get("example_penalty_when_policy_exists") or 0)
        score += example_penalty
        penalties["example_when_policy_exists"] = round(example_penalty, 4)

    if is_full_sop(candidate) and query_understanding.intent != "document_title":
        full_sop_penalty = float(stable.get("full_sop_penalty_for_specific_query") or 0)
        score += full_sop_penalty
        penalties["full_sop_specific_query"] = round(full_sop_penalty, 4)

    debug = {
        "mode": options.mode,
        "intent": query_understanding.intent,
        "query_understanding_used": query_understanding.source == "model",
        "meili_score": candidate.meili_score,
        "vector_score": candidate.vector_score,
        "fusion_score": candidate.fusion_score,
        "business_score": round(score, 4),
        "final_score": round(score, 4),
        "boosts": boosts,
        "penalties": penalties,
        "exact_phrase": exact_debug,
        "source_ref_quality": candidate.source_ref_quality,
    }
    return replace(candidate, business_score=score, final_score=score, score_debug=debug if options.debug else {})


def apply_duplicate_parent_penalties(
    candidates: list[SearchCandidate],
    config: dict[str, Any],
    debug: bool,
) -> list[SearchCandidate]:
    stable = config.get("stable_boosts") if isinstance(config.get("stable_boosts"), dict) else {}
    penalties_cfg = stable.get("duplicate_parent_penalty") if isinstance(stable.get("duplicate_parent_penalty"), dict) else {}
    seen: dict[str, int] = {}
    output: list[SearchCandidate] = []
    for candidate in candidates:
        key = candidate.parent_chunk_id or candidate.parent_section_id or candidate.parent_unit_id
        if not key:
            output.append(candidate)
            continue
        seen[key] = seen.get(key, 0) + 1
        penalty = 0.0
        if seen[key] == 2:
            penalty = float(penalties_cfg.get("second") or 0)
        elif seen[key] >= 3:
            penalty = float(penalties_cfg.get("third_or_more") or 0)
        if not penalty:
            output.append(candidate)
            continue
        score_debug = dict(candidate.score_debug or {})
        if debug:
            penalties = dict(score_debug.get("penalties") or {})
            penalties["duplicate_parent"] = round(penalty, 4)
            score_debug["penalties"] = penalties
            score_debug["business_score"] = round(candidate.business_score + penalty, 4)
            score_debug["final_score"] = round(candidate.final_score + penalty, 4)
        output.append(
            replace(
                candidate,
                business_score=candidate.business_score + penalty,
                final_score=candidate.final_score + penalty,
                score_debug=score_debug,
            )
        )
    return output


def maybe_model_rerank(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions,
    config: dict[str, Any] | None = None,
) -> tuple[list[SearchCandidate], dict[str, Any]]:
    config = config or load_ranking_config()
    decision = should_use_model_rerank(query, candidates, options, config)
    if not decision["use"]:
        return candidates, decision
    limit = min(
        int(mode_config(config, options.mode).get("model_rerank_limit") or settings.rerank_max_candidates),
        settings.rerank_max_candidates,
        len(candidates),
    )
    selected = candidates[:limit]
    cache_key = rerank_cache_key(query, selected, config)
    now = time.time()
    cached = _RERANK_CACHE.get(cache_key)
    if cached and cached[0] > now:
        relevance_by_id = cached[1]
        decision = {**decision, "cache": "hit"}
        logger.info("model_rerank_cache_hit", extra={"event": "model_rerank_cache_hit", "mode": options.mode})
    else:
        logger.info("model_rerank_cache_miss", extra={"event": "model_rerank_cache_miss", "mode": options.mode})
        try:
            relevance_by_id = rerank_with_provider(query, selected, options, config)
            _RERANK_CACHE[cache_key] = (now + settings.rerank_cache_ttl_seconds, relevance_by_id)
            decision = {**decision, "cache": "miss"}
        except Exception as exc:
            logger.warning("model_rerank_failed", extra={"event": "model_rerank_failed", "provider": settings.rerank_provider, "error": exc.__class__.__name__})
            return candidates, {**decision, "use": False, "skip_reason": f"model_rerank_failed:{exc.__class__.__name__}", "fallback": "business_ranking"}

    risk_sensitive = bool((options.query_understanding or QueryUnderstanding()).risk_sensitive)
    blended: list[SearchCandidate] = []
    for candidate in candidates:
        relevance = relevance_by_id.get(candidate.chunk_id)
        if relevance is None:
            blended.append(candidate)
            continue
        if options.mode == "portal_search":
            business_weight, model_weight = 0.75, 0.25
        elif risk_sensitive or candidate.risk_level in {"critical", "high"}:
            business_weight, model_weight = 0.55, 0.45
        else:
            business_weight, model_weight = 0.45, 0.55
        final_score = candidate.business_score * business_weight + relevance * 100 * model_weight
        score_debug = dict(candidate.score_debug or {})
        if options.debug:
            score_debug.update(
                {
                    "model_relevance": round(relevance, 4),
                    "model_rerank_score": round(relevance, 4),
                    "final_score": round(final_score, 4),
                    "rerank_used": True,
                    "rerank_provider": settings.rerank_provider,
                    "rerank_reason": decision.get("reason", ""),
                }
            )
        blended.append(replace(candidate, model_rerank_score=relevance, final_score=final_score, score_debug=score_debug))
    return sorted(blended, key=candidate_sort_key, reverse=True), decision


def should_use_model_rerank(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions,
    config: dict[str, Any],
) -> dict[str, Any]:
    if options.mode != "ai_chat" and not settings.rerank_enable_for_portal:
        return {"use": False, "skip_reason": "model_rerank_disabled_for_mode"}
    mode_enabled = bool(mode_config(config, options.mode).get("model_rerank_enabled", False))
    if options.mode == "ai_chat":
        mode_enabled = mode_enabled and settings.rerank_enable_for_ai_chat
    if options.force_model_rerank is not None:
        mode_enabled = options.force_model_rerank
    if not mode_enabled:
        return {"use": False, "skip_reason": "model_rerank_disabled"}
    provider = settings.rerank_provider
    if provider == "none":
        return {"use": False, "skip_reason": "rerank_provider_none"}
    gate = config.get("model_rerank_gate") if isinstance(config.get("model_rerank_gate"), dict) else {}
    minimum_candidates = int(gate.get("minimum_candidates") or 3)
    if len(candidates) < minimum_candidates:
        return {"use": False, "skip_reason": "too_few_candidates"}
    total_chars = sum(len(candidate.text_for_rerank()) for candidate in candidates[: settings.rerank_max_candidates])
    if total_chars > int(gate.get("maximum_total_candidate_chars") or 22000):
        return {"use": False, "skip_reason": "candidate_text_too_large"}
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    strong_exact = float((top.score_debug or {}).get("boosts", {}).get("exact_phrase") or 0) >= float((config.get("stable_boosts") or {}).get("strong_exact_phrase_threshold") or 22)
    if strong_exact:
        return {"use": False, "skip_reason": "strong_exact_phrase_top_result"}
    if second and top.business_score - second.business_score >= float((config.get("stable_boosts") or {}).get("strong_top_gap") or 18):
        return {"use": False, "skip_reason": "strong_business_score_gap"}
    query_understanding = options.query_understanding or QueryUnderstanding()
    word_count = len([token for token in normalize_text(query).split() if token])
    semantic_query = word_count >= int(gate.get("semantic_query_min_words") or 5)
    source_disagreement = any(candidate.from_meilisearch and not candidate.from_vector for candidate in candidates[:5]) and any(
        candidate.from_vector and not candidate.from_meilisearch for candidate in candidates[:5]
    )
    uncertain_high_risk = query_understanding.risk_sensitive and (not second or top.business_score - second.business_score < 12)
    if semantic_query or source_disagreement or uncertain_high_risk or (query_understanding.confidence >= 0.65 and query_understanding.intent != "generic"):
        return {"use": True, "reason": "semantic_or_uncertain_ai_chat", "provider": provider}
    return {"use": False, "skip_reason": "gate_conditions_not_met"}


def rerank_with_provider(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions,
    config: dict[str, Any],
) -> dict[str, float]:
    provider = settings.rerank_provider
    if provider == "llm":
        return llm_listwise_rerank(query, candidates, options, config)
    if provider == "custom":
        return custom_http_rerank(query, candidates, options, config)
    if provider == "cohere":
        return cohere_rerank(query, candidates)
    raise ValueError(f"unsupported_rerank_provider:{provider}")


def llm_listwise_rerank(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions,
    config: dict[str, Any],
) -> dict[str, float]:
    if not settings.openrouter_api_key:
        raise ValueError("openrouter_disabled")
    candidate_payload = [
        {
            "chunk_id": candidate.chunk_id,
            "title": candidate.title,
            "chunk_type": candidate.chunk_type,
            "risk_level": candidate.risk_level,
            "source_ref_quality": candidate.source_ref_quality,
            "text": candidate.text_for_rerank(max_chars=1100),
        }
        for candidate in candidates
    ]
    payload = {
        "model": settings.rerank_model_name or settings.openrouter_chat_simple_model or settings.openrouter_chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are reranking SOP search candidates for a customer support knowledge base. "
                    "You do not answer the user. You only rank candidates by how directly they answer the query. "
                    "You must not invent policy. Prefer current published policy chunks and exact source-backed chunks. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Query:\n{query}\n\n"
                    f"Query understanding:\n{json.dumps((options.query_understanding or QueryUnderstanding()).as_debug(), ensure_ascii=False)}\n\n"
                    f"Candidates:\n{json.dumps(candidate_payload, ensure_ascii=False)}\n\n"
                    "Ranking rules:\n"
                    "- Prefer candidates that directly answer the query.\n"
                    "- Prefer grouped rule chunks for comparison, conditions, when-to-use, có được, or trường hợp queries.\n"
                    "- Prefer atomic rule chunks for exact forbidden phrase, exact macro, or exact wording queries.\n"
                    "- Prefer compliance_rule/compliance_rule_group for sanction, internal workflow, disclosure, or forbidden-action questions.\n"
                    "- Prefer wording_rule_group/wording_rule for xin lỗi, rất tiếc, xưng hô, quý khách.\n"
                    "- Do not rank examples above policy rules unless the example is the only direct match.\n"
                    "- Do not rank full_sop above a direct atomic/grouped rule unless the query asks for the whole document.\n"
                    "- Penalize candidates with weak or missing source refs.\n\n"
                    "Return JSON: {\"ranked\":[{\"chunk_id\":\"string\",\"relevance\":0.0,\"reason\":\"short internal debug reason\"}]}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    data = openrouter_chat_json(payload, timeout_seconds=max(1.0, settings.rerank_timeout_ms / 1000))
    return normalize_rerank_payload(data, {candidate.chunk_id for candidate in candidates})


def custom_http_rerank(
    query: str,
    candidates: list[SearchCandidate],
    options: RankingOptions,
    config: dict[str, Any],
) -> dict[str, float]:
    if not settings.rerank_custom_url:
        raise ValueError("custom_rerank_url_missing")
    payload = {
        "query": query,
        "query_understanding": (options.query_understanding or QueryUnderstanding()).as_debug(),
        "candidates": [{"chunk_id": candidate.chunk_id, "text": candidate.text_for_rerank()} for candidate in candidates],
        "config_version": config.get("version"),
    }
    with httpx.Client(timeout=max(1.0, settings.rerank_timeout_ms / 1000)) as client:
        response = client.post(settings.rerank_custom_url, json=payload)
        response.raise_for_status()
        return normalize_rerank_payload(response.json(), {candidate.chunk_id for candidate in candidates})


def cohere_rerank(query: str, candidates: list[SearchCandidate]) -> dict[str, float]:
    if not settings.cohere_api_key:
        raise ValueError("cohere_api_key_missing")
    payload = {
        "query": query,
        "documents": [candidate.text_for_rerank() for candidate in candidates],
        "top_n": len(candidates),
        "model": settings.rerank_model_name or "rerank-v3.5",
    }
    headers = {"Authorization": f"Bearer {settings.cohere_api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=max(1.0, settings.rerank_timeout_ms / 1000)) as client:
        response = client.post("https://api.cohere.com/v2/rerank", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    output: dict[str, float] = {}
    for item in data.get("results") or []:
        try:
            index = int(item.get("index"))
            relevance = float(item.get("relevance_score"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(candidates):
            output[candidates[index].chunk_id] = max(0.0, min(1.0, relevance))
    if not output:
        raise ValueError("cohere_empty_rerank")
    return output


def normalize_rerank_payload(payload: Any, allowed_ids: set[str]) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise ValueError("rerank_invalid_shape")
    ranked = payload.get("ranked")
    if not isinstance(ranked, list):
        raise ValueError("rerank_missing_ranked")
    output: dict[str, float] = {}
    for item in ranked:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id not in allowed_ids:
            continue
        try:
            relevance = float(item.get("relevance"))
        except (TypeError, ValueError):
            continue
        output[chunk_id] = max(0.0, min(1.0, relevance))
    if not output:
        raise ValueError("rerank_no_valid_ids")
    return output


def openrouter_chat_json(payload: dict[str, Any], timeout_seconds: float) -> Any:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(f"{settings.openrouter_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
    return json.loads(extract_json_object(content))


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0)
    raise ValueError("json_object_not_found")


def candidates_from_rows(rows: list[dict[str, Any]], source: str = "") -> list[SearchCandidate]:
    output = []
    for rank, row in enumerate(rows, start=1):
        output.append(candidate_from_row(row, source=source, rank=rank))
    return output


def candidate_from_row(row: dict[str, Any], source: str = "", rank: int | None = None) -> SearchCandidate:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_refs = tuple(ref for ref in metadata.get("source_refs", []) if isinstance(ref, dict))
    chunk_type = first_text(metadata.get("chunk_type"), metadata.get("unit_type"), row.get("section"))
    if chunk_type == "grouped_parent":
        chunk_type = f"{first_text(metadata.get('unit_type'), row.get('section'))}_group"
    retrieval_text = first_text(metadata.get("retrieval_text"), row.get("retrieval_text"), row.get("content"))
    display_text = first_text(metadata.get("display_text"), row.get("display_text"), row.get("content"))
    section_path = tuple(str(item) for item in metadata.get("section_path", []) if str(item).strip()) if isinstance(metadata.get("section_path"), list) else ()
    meili_score = float(row.get("meili_score") or (row.get("score") if source in {"meilisearch", "lexical"} else 0) or 0)
    vector_score = float(row.get("vector_score") or (row.get("score") if source == "vector" else 0) or 0)
    lexical_score = float(row.get("lexical_score") or (row.get("score") if source in {"lexical", "meilisearch"} else 0) or 0)
    return SearchCandidate(
        chunk_id=str(row.get("chunk_id") or row.get("id") or ""),
        document_id=str(row.get("document_id") or ""),
        document_version_id=str(row.get("document_version_id") or row.get("version_id") or ""),
        parent_section_id=first_text(metadata.get("parent_section_id"), metadata.get("section_id")),
        parent_chunk_id=first_text(metadata.get("parent_chunk_id")),
        parent_unit_id=first_text(metadata.get("parent_unit_id")),
        title=first_text(row.get("heading"), metadata.get("title"), row.get("title")),
        normalized_title=first_text(metadata.get("normalized_title"), normalize_text(row.get("heading") or row.get("title") or "")),
        content=str(row.get("content") or ""),
        retrieval_text=retrieval_text,
        display_text=display_text,
        section_path=section_path,
        chunk_type=chunk_type,
        status=first_text(row.get("status"), metadata.get("status"), "published"),
        review_status=first_text(row.get("review_status"), metadata.get("review_status")),
        risk_level=first_text(row.get("risk_level"), metadata.get("risk_level"), "low"),
        source_ref_quality=first_text(metadata.get("source_ref_quality"), derive_source_ref_quality(source_refs, metadata)),
        source_refs=source_refs,
        category=first_text(row.get("category"), metadata.get("category")),
        collections=tuple(collection_values(metadata.get("collections") or metadata.get("collection_slug"))),
        audience=tuple(string_list(row.get("audience") or metadata.get("audience"))),
        vertical=first_text(row.get("vertical"), metadata.get("vertical")),
        updated_at=first_text(row.get("updated_at"), metadata.get("updated_at")),
        effective_from=first_text(row.get("effective_from"), metadata.get("effective_from"), metadata.get("effective_date")),
        is_current_version=bool(row.get("is_current_version", metadata.get("is_current_version", True))),
        macro_text=first_text(metadata.get("macro_text"), metadata.get("retrieval_text") if chunk_type in {"macro_script", "macro_table"} else ""),
        forbidden_phrases=string_tuple(metadata.get("forbidden_phrases")),
        keywords=string_tuple(metadata.get("keywords")),
        meili_score=meili_score,
        vector_score=vector_score,
        lexical_score=lexical_score,
        fusion_score=float(row.get("fusion_score") or 0),
        from_meilisearch=bool(row.get("from_meilisearch") or source == "meilisearch"),
        from_vector=bool(row.get("from_vector") or source == "vector" or "vector" in (row.get("rank_source") or [])),
        meili_rank=rank if source == "meilisearch" else int_or_none(row.get("meili_rank")),
        vector_rank=rank if source == "vector" else int_or_none(row.get("vector_rank")),
        raw_row=dict(row),
    )


def rows_from_candidates(candidates: list[SearchCandidate], debug: bool = False) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        row = dict(candidate.raw_row)
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if debug and candidate.score_debug:
            metadata = {**metadata, "score_debug": candidate.score_debug}
            row["score_debug"] = candidate.score_debug
        row["metadata"] = metadata
        row["score"] = candidate.final_score
        row["business_score"] = candidate.business_score
        row["final_score"] = candidate.final_score
        row["meili_score"] = candidate.meili_score
        row["vector_score"] = candidate.vector_score
        row["lexical_score"] = candidate.lexical_score
        row["fusion_score"] = candidate.fusion_score
        rank_source = list(row.get("rank_source") or [])
        if candidate.lexical_score > 0 and not candidate.from_meilisearch and "lexical" not in rank_source:
            rank_source.append("lexical")
        if candidate.from_meilisearch and "meilisearch" not in rank_source:
            rank_source.append("meilisearch")
        if candidate.from_vector and "vector" not in rank_source:
            rank_source.append("vector")
        row["rank_source"] = list(dict.fromkeys(rank_source))
        rows.append(row)
    return rows


def merge_candidates(
    keyword_candidates: list[SearchCandidate],
    vector_candidates: list[SearchCandidate],
    limit: int,
    config: dict[str, Any] | None = None,
) -> list[SearchCandidate]:
    config = config or load_ranking_config()
    stable = config.get("stable_boosts") if isinstance(config.get("stable_boosts"), dict) else {}
    by_id: dict[str, SearchCandidate] = {}
    for index, candidate in enumerate(keyword_candidates, start=1):
        by_id[candidate.chunk_id] = replace(candidate, meili_rank=candidate.meili_rank or index)
    for index, candidate in enumerate(vector_candidates, start=1):
        existing = by_id.get(candidate.chunk_id)
        if not existing:
            by_id[candidate.chunk_id] = replace(candidate, from_vector=True, vector_rank=candidate.vector_rank or index)
            continue
        meili_rank = existing.meili_rank or 999
        vector_rank = candidate.vector_rank or index
        rrf = 1.0 / (RRF_K + meili_rank) + 1.0 / (RRF_K + vector_rank)
        fusion_score = float(stable.get("fusion_bonus") or 8) + rrf * float(stable.get("rrf_weight") or 100)
        keyword_label = "meilisearch" if existing.from_meilisearch else "lexical"
        merged_sources = list(dict.fromkeys([*(existing.raw_row.get("rank_source") or []), *(candidate.raw_row.get("rank_source") or []), keyword_label, "vector"]))
        raw_row = {
            **existing.raw_row,
            "rank_source": merged_sources,
            "meili_score": max(existing.meili_score, candidate.meili_score),
            "vector_score": max(existing.vector_score, candidate.vector_score),
            "fusion_score": fusion_score,
            "from_meilisearch": existing.from_meilisearch,
            "from_vector": True,
            "meili_rank": meili_rank,
            "vector_rank": vector_rank,
        }
        by_id[candidate.chunk_id] = replace(
            existing,
            from_vector=True,
            vector_rank=vector_rank,
            vector_score=max(existing.vector_score, candidate.vector_score),
            fusion_score=fusion_score,
            raw_row=raw_row,
        )
    return sorted(by_id.values(), key=lambda item: (item.fusion_score, item.meili_score, item.vector_score), reverse=True)[:limit]


def exact_phrase_boost(query: str, candidate: SearchCandidate, stable_boosts: dict[str, Any], extra_phrases: tuple[str, ...] = ()) -> tuple[float, dict[str, Any]]:
    exact_cfg = stable_boosts.get("exact_phrase") if isinstance(stable_boosts.get("exact_phrase"), dict) else {}
    phrases = exact_phrases(query, extra_phrases)
    if not phrases:
        return 0.0, {"matched": []}
    fields = {
        "title": candidate.title,
        "normalized_title": candidate.normalized_title,
        "section_path": " ".join(candidate.section_path),
        "macro_text": candidate.macro_text,
        "forbidden_phrases": " ".join(candidate.forbidden_phrases),
        "content": f"{candidate.retrieval_text} {candidate.content}",
    }
    total = 0.0
    matched: list[dict[str, Any]] = []
    for field_name, field_value in fields.items():
        field_text = normalize_text(field_value)
        if not field_text:
            continue
        for phrase in phrases:
            if phrase and phrase in field_text:
                weight = float(exact_cfg.get(field_name) or 0)
                if weight:
                    total += weight
                    matched.append({"field": field_name, "phrase": phrase, "weight": weight})
                break
    return min(total, float(exact_cfg.get("max_total") or total)), {"matched": matched, "raw_total": round(total, 4)}


def exact_phrases(query: str, extra_phrases: tuple[str, ...] = ()) -> list[str]:
    phrases = [normalize_text(match) for match in re.findall(r'"([^"]+)"|“([^”]+)”', query) for match in match if match]
    phrases.extend(normalize_text(phrase) for phrase in extra_phrases if normalize_text(phrase))
    normalized_query = normalize_text(query.strip('"“” '))
    if normalized_query and len(normalized_query) >= 3:
        phrases.append(normalized_query)
    return list(dict.fromkeys(phrases))


def chunk_type_priority(candidate: SearchCandidate, intent: str, config: dict[str, Any]) -> float:
    priorities = config.get("chunk_type_priorities") if isinstance(config.get("chunk_type_priorities"), dict) else {}
    intent_map = priorities.get(intent) if isinstance(priorities.get(intent), dict) else {}
    generic_map = priorities.get("generic") if isinstance(priorities.get("generic"), dict) else {}
    for key in ranking_chunk_type_keys(candidate):
        if key in intent_map:
            return float(intent_map.get(key) or 0)
        if key in generic_map:
            return float(generic_map.get(key) or 0)
    return 0.0


def ranking_chunk_type_keys(candidate: SearchCandidate) -> list[str]:
    metadata = candidate.raw_row.get("metadata") if isinstance(candidate.raw_row.get("metadata"), dict) else {}
    unit_type = first_text(metadata.get("unit_type"), candidate.raw_row.get("section"))
    raw_chunk_type = first_text(metadata.get("chunk_type"), candidate.chunk_type)
    keys: list[str] = []
    if raw_chunk_type == "grouped_parent" and unit_type:
        keys.append(f"{unit_type}_group")
    if raw_chunk_type in {"atomic_child", "parent_table"} and unit_type:
        keys.append(unit_type)
    if candidate.chunk_type:
        keys.append(candidate.chunk_type)
    if unit_type:
        keys.append(unit_type)
    if raw_chunk_type:
        keys.append(raw_chunk_type)
    return list(dict.fromkeys(key for key in keys if key))


def status_weight(candidate: SearchCandidate, stable: dict[str, Any]) -> float:
    status_cfg = stable.get("status") if isinstance(stable.get("status"), dict) else {}
    candidates = [candidate.status, candidate.review_status]
    for value in candidates:
        value_text = normalize_key(value)
        if value_text in status_cfg:
            return float(status_cfg.get(value_text) or 0)
    return 0.0


def map_weight(mapping: Any, key: str) -> float:
    if not isinstance(mapping, dict):
        return 0.0
    return float(mapping.get(normalize_key(key), mapping.get(str(key), 0)) or 0)


def any_policy_candidate(candidates: list[SearchCandidate]) -> bool:
    return any(not is_example(candidate) and ("rule" in candidate.chunk_type or candidate.chunk_type in {"macro_script", "macro_table", "operational_note"}) for candidate in candidates)


def is_example(candidate: SearchCandidate) -> bool:
    return candidate.chunk_type == "example" or "example" in normalize_key(candidate.title)


def is_full_sop(candidate: SearchCandidate) -> bool:
    return candidate.chunk_type == "full_sop"


def candidate_sort_key(candidate: SearchCandidate) -> tuple[float, float, float, float, int]:
    return (
        candidate.final_score,
        candidate.business_score,
        candidate.meili_score,
        candidate.vector_score,
        -(candidate.meili_rank or candidate.vector_rank or 9999),
    )


def derive_source_ref_quality(source_refs: tuple[dict[str, Any], ...], metadata: dict[str, Any]) -> str:
    if metadata.get("row_index") is not None or metadata.get("table_id") or metadata.get("table_index") is not None:
        return "table_row"
    for ref in source_refs:
        if ref.get("row_index") is not None and ref.get("table_index") is not None:
            return "table_row"
    if metadata.get("block_id") or any(ref.get("block_id") for ref in source_refs):
        return "block_id"
    if any(ref.get("paragraph_index") is not None for ref in source_refs):
        return "paragraph_only"
    return "none"


def rerank_cache_key(query: str, candidates: list[SearchCandidate], config: dict[str, Any]) -> str:
    return stable_hash(
        {
            "query": query,
            "candidate_ids": [candidate.chunk_id for candidate in candidates],
            "provider": settings.rerank_provider,
            "model": settings.rerank_model_name,
            "prompt_version": settings.rerank_prompt_version,
            "config_version": config.get("version"),
        }
    )


def stable_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_text(value: Any) -> str:
    text = str(value or "")
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped.replace("đ", "d").replace("Đ", "D").lower()).strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", normalize_text(value)).strip("_")


def string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(string_list(value))


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item).strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def collection_values(value: Any) -> list[str]:
    if isinstance(value, list):
        output = []
        for item in value:
            if isinstance(item, dict):
                output.append(first_text(item.get("slug"), item.get("id"), item.get("name")))
            elif str(item).strip():
                output.append(str(item))
        return [item for item in output if item]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
