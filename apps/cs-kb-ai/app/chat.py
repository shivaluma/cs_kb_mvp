from __future__ import annotations

import time
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from app import repository
from app.config import settings
from app.openrouter import generate_chat_session_title, generate_grounded_answer
from app.retrieval import retrieve, to_result
from app.schemas import ChatSessionMessageRequest, GroundedChatRequest, GroundedChatResponse, RetrievalFilters, RetrievalRequest, RetrievalResponse, RetrievalResult


DIRECT_SOP_UNIT_TYPES = {
    "full_sop",
    "policy_rule",
    "exception_rule",
    "handling_rule",
    "routing_rule",
    "operational_instruction",
    "validation_rule",
    "decision_rule",
    "sla_rule",
    "escalation_rule",
    "case_creation_rule",
    "handoff_rule",
    "workflow_overview",
    "workflow_graph",
    "workflow_step",
    "decision_point",
    "warning",
    "operational_note",
    "macro_script",
    "security_note",
    "compliance_note",
}
INDEX_UNIT_TYPES = {
    "issue_router_unit",
    "sop_reference",
    "vip_overlay_rule",
    "product_update_note",
    "tool_link",
    "quick_action_rule",
}
POLICY_SOURCE_ROLES = {"direct_sop", "related_sop"}
SOURCE_ROLE_ORDER = {
    "direct_sop": 0,
    "issue_router": 1,
    "related_sop": 2,
    "action_template": 3,
    "tool_link": 4,
    "parent_sop": 5,
}
SOURCE_GROUP_LABELS = {
    "direct_sop": "Direct SOP",
    "issue_router": "Issue router",
    "related_sop": "Related SOP",
    "action_template": "Action templates",
    "tool_link": "Tools",
    "parent_sop": "Parent SOP",
}
FOLLOW_UP_MARKERS = (
    "cái đó",
    "cai do",
    "vậy",
    "vay",
    "nó",
    "no",
    "tiếp",
    "tiep",
    "ở trên",
    "o tren",
    "trên",
    "tren",
    "khác gì",
    "khac gi",
    "thì sao",
    "thi sao",
    "còn",
    "con",
)

CHANNEL_GROUPS = {"hotline", "chat_social", "call_in_app", "mail"}
EXCLUSIVE_CONTEXT_GROUPS = {
    "si_lock",
    "foreign_customer",
    "betaxi",
    "gsm",
    "taxi_phone",
}
INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "tx": ("tx", "tai xe", "tai xế", "tài xế"),
    "kh": ("kh", "khach hang", "khách hàng"),
    "hotline": ("hotline", "1900232345"),
    "chat_social": ("chat social",),
    "call_in_app": ("call in app", "cia", "non voice", "non-voice", "chat in app"),
    "mail": ("mail", "email", "ho.tro", "hotro@be.com.vn"),
    "alternate_number": ("so khac", "sdt khac", "goi sang so", "goi ra so", "lien he ra 1 so", "lien he so dien thoai khac"),
    "cs_outbound_reflection": ("cs goi tx", "cs lien he tx", "xu ly phan anh", "kh phan anh"),
    "tx_inbound": ("tx chu dong", "tx lien he", "tai xe lien he", "goi vao"),
    "si_lock": ("si", "bi khoa", "tam khoa", "khoa tai khoan"),
    "foreign_customer": ("nuoc ngoai", "ngoai ngu", "tieng anh", "tieng viet"),
    "betaxi": ("betaxi", "be taxi"),
    "gsm": ("gsm", "xanh sm"),
    "taxi_phone": ("so dien thoai hang taxi", "hang taxi", "thanh nga", "van xuan", "thang long"),
    "email": ("email", "e-mail"),
    "current_trip": ("chuyen dang loi", "chuyen can ho tro", "trip hien tai", "don dang loi"),
    "completed_trip": ("chuyen hoan thanh gan nhat", "trip hoan thanh gan nhat", "khong phai chuyen xe can ho tro"),
}


@dataclass(frozen=True)
class ChatModelSelection:
    route: str
    model: str
    reason: str
    strict_grounding: bool
    fallback_model: str


@dataclass(frozen=True)
class ChatRetrievalBundle:
    retrieval: RetrievalResponse
    source_groups: list[dict[str, Any]]
    trace: dict[str, Any]


def grounded_chat(request: GroundedChatRequest) -> GroundedChatResponse:
    started_at = time.perf_counter()
    bundle = retrieve_for_chat(request)
    retrieval = bundle.retrieval

    warnings = [
        "grounded_published_sop_units_only",
        "raw_draft_archived_content_excluded",
        "chat_kb_index_multi_stage_retrieval",
        *retrieval.warnings,
    ]
    if not retrieval.results:
        selection = select_chat_model(request, retrieval)
        response = GroundedChatResponse(
            question=request.question,
            answer="Không tìm thấy SOP published đủ tin cậy để trả lời. Hãy thử query khác, mở SOP Lookup, hoặc escalate Lead.",
            steps=[],
            warnings=[*warnings, "missing_published_sources"],
            citations=[],
            sources=[],
            confidence=0,
            retrieval=retrieval,
            source_groups=bundle.source_groups,
            retrieval_trace=bundle.trace,
            latency_ms=elapsed_ms(started_at),
            model_route=selection.route,
            model_used=selection.model,
            model_reason=selection.reason,
        )
        repository.log_chat(response)
        return response

    selection = select_chat_model(request, retrieval)
    if not has_policy_source(retrieval.results):
        response = GroundedChatResponse(
            question=request.question,
            answer=(
                "Tìm thấy chỉ mục, tool hoặc action template liên quan, nhưng chưa có SOP published/approved "
                "được link đủ để kết luận chính sách. Hãy mở nguồn bên dưới, assign/approve relation tới SOP target, "
                "hoặc escalate Lead trước khi xử lý."
            ),
            steps=[],
            warnings=[*warnings, "index_context_without_policy_source"],
            citations=[],
            sources=retrieval.results,
            confidence=0.15,
            retrieval=retrieval,
            source_groups=bundle.source_groups,
            retrieval_trace=bundle.trace,
            latency_ms=elapsed_ms(started_at),
            model_route=selection.route,
            model_used=selection.model,
            model_reason=selection.reason,
        )
        repository.log_chat(response)
        return response

    answer, answer_warnings = generate_grounded_answer(
        request.question,
        retrieval,
        [message.model_dump() for message in request.conversation],
        session_summary=request.session_summary,
        recent_user_context=request.recent_user_context,
        model=selection.model,
        strict_grounding=selection.strict_grounding,
    )
    used_model = selection.model
    if answer is None and selection.fallback_model and selection.fallback_model != selection.model:
        fallback_answer, fallback_warnings = generate_grounded_answer(
            request.question,
            retrieval,
            [message.model_dump() for message in request.conversation],
            session_summary=request.session_summary,
            recent_user_context=request.recent_user_context,
            model=selection.fallback_model,
            strict_grounding=True,
        )
        answer_warnings = [*answer_warnings, "primary_chat_model_failed_trying_fallback", *fallback_warnings]
        if fallback_answer is not None:
            answer = fallback_answer
            used_model = selection.fallback_model
    warnings.extend(answer_warnings)
    if answer is None:
        response = GroundedChatResponse(
            question=request.question,
            answer="Không thể tạo câu trả lời grounded từ model lúc này. Các SOP sources bên dưới vẫn là published curated units, hãy mở source để xử lý hoặc thử lại.",
            steps=[],
            warnings=warnings,
            citations=retrieval.citations[: request.limit],
            sources=retrieval.results,
            confidence=0,
            retrieval=retrieval,
            source_groups=bundle.source_groups,
            retrieval_trace=bundle.trace,
            latency_ms=elapsed_ms(started_at),
            model_route=selection.route,
            model_used=used_model,
            model_reason=selection.reason,
        )
        repository.log_chat(response)
        return response

    source_indices = [index for index in answer.source_indices if 1 <= index <= len(retrieval.results)]
    cited_results = [retrieval.results[index - 1] for index in source_indices]
    citations = [result.citation for result in cited_results]
    if not citations:
        warnings.append("no_valid_citation_after_filter")
        answer_text = "Không tìm thấy SOP published đủ căn cứ để trả lời chắc chắn. Vui lòng mở Lookup hoặc escalate Lead để xác nhận."
        steps: list[str] = []
        confidence = 0.0
    else:
        answer_text = answer.answer
        steps = answer.steps
    unresolved_dependencies = repository.unresolved_relations_for_chunks([result.chunk_id for result in cited_results or retrieval.results])
    if unresolved_dependencies:
        warnings.append("matched_source_has_unresolved_dependency")
        dependency_titles = list(dict.fromkeys([str(item.get("target_title") or "") for item in unresolved_dependencies if item.get("target_title")]))[:3]
        if dependency_titles:
            answer_text = (
                f"{answer_text}\n\n"
                "Lưu ý: Source có nhắc tới SOP/tài liệu liên quan chưa được link trong KB: "
                f"{'; '.join(dependency_titles)}. Không dùng nội dung của dependency này cho câu trả lời cho tới khi relation được duyệt."
            )
    confidence = evidence_confidence(
        request.question,
        retrieval.results,
        cited_results,
        float(answer.confidence or 0),
        bool(unresolved_dependencies),
    ) if citations else 0.0
    if citations and abs(confidence - float(answer.confidence or 0)) >= 0.12:
        warnings.append("model_confidence_overridden_by_evidence_score")

    response = GroundedChatResponse(
        question=request.question,
        answer=answer_text,
        steps=steps,
        warnings=[*warnings, *answer.warnings],
        citations=citations,
        sources=cited_results or retrieval.results,
        confidence=confidence,
        retrieval=retrieval,
        source_groups=bundle.source_groups,
        retrieval_trace=bundle.trace,
        latency_ms=elapsed_ms(started_at),
        model_route=selection.route,
        model_used=used_model,
        model_reason=selection.reason,
    )
    repository.log_chat(response)
    return response


def retrieve_for_chat(request: GroundedChatRequest) -> ChatRetrievalBundle:
    base_filters = request.filters.model_copy(update={"status": ["published"]})
    direct_limit = max(request.limit, 10)
    index_limit = max(6, min(request.limit, 10))
    query_text = request.retrieval_query.strip() or request.question
    context_limit = chat_context_limit(query_text, request.limit)

    direct_retrieval = retrieve(
        RetrievalRequest(
            query=query_text,
            filters=filters_with_unit_types(base_filters, DIRECT_SOP_UNIT_TYPES),
            limit=direct_limit,
            mode="hybrid",
        ),
        include_relation_expansion=False,
    )
    index_retrieval = retrieve(
        RetrievalRequest(
            query=query_text,
            filters=filters_with_unit_types(base_filters, INDEX_UNIT_TYPES),
            limit=index_limit,
            mode="hybrid",
        ),
        include_relation_expansion=False,
    )

    direct_candidates = [
        annotate_result(result, "direct_sop", "direct_policy_unit")
        for result in direct_retrieval.results
    ]
    index_candidates = [
        annotate_result(result, index_source_role(result), "kb_index_match")
        for result in index_retrieval.results
    ]
    direct_results = rerank_stage_results(query_text, direct_candidates)
    index_results = rerank_stage_results(query_text, index_candidates)
    initial_results = dedupe_results([*direct_results, *index_results])
    relation_seed_results = relation_seed_candidates(initial_results, context_limit)
    exclude_ids = [result.chunk_id for result in initial_results]
    relation_rows = repository.approved_relation_target_rows_for_chunks(
        [result.chunk_id for result in relation_seed_results],
        [*exclude_ids],
        max(4, request.limit // 2),
    )
    related_results = [
        annotate_result(to_result(row), "related_sop", "approved_relation_expansion")
        for row in relation_rows
    ]
    related_results = rerank_stage_results(query_text, related_results)
    exclude_ids.extend(result.chunk_id for result in related_results)
    parent_rows = repository.parent_sop_context_rows(
        [result.chunk_id for result in relation_seed_candidates([*direct_results, *related_results], context_limit)],
        [*exclude_ids],
        max(2, request.limit // 4),
    )
    parent_results = [
        annotate_result(to_result(row), "parent_sop", "parent_full_sop_context")
        for row in parent_rows
    ]
    context_candidates = [*direct_results, *index_results, *related_results, *parent_results]
    deduped_context_candidates = semantic_dedupe_results(context_candidates)
    final_results = rank_chat_results(context_candidates, context_limit)
    warnings = list(
        dict.fromkeys(
            [
                *direct_retrieval.warnings,
                *[f"index_{warning}" for warning in index_retrieval.warnings],
            ]
        )
    )
    if initial_results and not relation_rows:
        warnings.append("no_approved_relation_expansion")
    if not final_results:
        warnings.append("no_reliable_source")

    retrieval = RetrievalResponse(
        query=query_text,
        normalized_query=direct_retrieval.normalized_query or index_retrieval.normalized_query,
        query_expansion=direct_retrieval.query_expansion or index_retrieval.query_expansion,
        mode="hybrid",
        results=final_results,
        citations=[result.citation for result in final_results],
        warnings=warnings,
        latency_ms=direct_retrieval.latency_ms + index_retrieval.latency_ms,
    )
    trace = {
        "strategy": "chat_kb_index_multi_stage",
        "direct_count": len(direct_candidates),
        "index_count": len(index_candidates),
        "relation_count": len(related_results),
        "parent_count": len(parent_results),
        "direct_context_count": len([result for result in final_results if source_role(result) == "direct_sop"]),
        "index_context_count": len([result for result in final_results if source_role(result) == "issue_router"]),
        "related_context_count": len([result for result in final_results if source_role(result) == "related_sop"]),
        "parent_context_count": len([result for result in final_results if source_role(result) == "parent_sop"]),
        "final_count": len(final_results),
        "candidate_count": len(direct_candidates) + len(index_candidates) + len(related_results) + len(parent_results),
        "semantic_deduped_count": max(0, len(dedupe_results(context_candidates)) - len(deduped_context_candidates)),
        "relation_seed_count": len(relation_seed_results),
        "scope_filters": base_filters.model_dump(),
        "retrieval_query_used": query_text != request.question,
    }
    return ChatRetrievalBundle(
        retrieval=retrieval,
        source_groups=source_groups(final_results),
        trace=trace,
    )


def grounded_chat_session_message(session_id: str, payload: ChatSessionMessageRequest) -> dict[str, object]:
    session = repository.chat_session_by_id(session_id)
    if session["status"] != "active":
        raise ValueError("chat_session_archived")

    recent_user_context = repository.recent_chat_user_messages(session_id, 2)
    retrieval_query = contextual_retrieval_query(payload.question, recent_user_context, str(session.get("summary") or ""))
    token_context_metadata = {
        "recent_user_context": recent_user_context,
        "session_summary_chars": len(str(session.get("summary") or "")),
        "retrieval_query_used": retrieval_query != payload.question,
    }
    user_message = repository.insert_chat_message(
        session_id,
        "user",
        payload.question,
        token_context_metadata=token_context_metadata,
    )
    request = GroundedChatRequest(
        question=payload.question,
        retrieval_query=retrieval_query if retrieval_query != payload.question else "",
        session_summary=str(session.get("summary") or "")[:600],
        recent_user_context=recent_user_context,
        filters=payload.filters,
        limit=payload.limit,
        conversation=[],
        model_route=payload.model_route,
    )
    response = grounded_chat(request)
    title = ""
    if int(session.get("message_count") or 0) == 0 or str(session.get("title") or "") in {"", "New chat"}:
        title, title_warnings = generate_chat_session_title(payload.question)
        response.warnings = [*response.warnings, *title_warnings]
    source_chunk_ids = [citation.chunk_id for citation in response.citations]
    assistant_message = repository.insert_chat_message(
        session_id,
        "assistant",
        response.answer,
        response_payload=response.model_dump(mode="json"),
        source_chunk_ids=source_chunk_ids,
        token_context_metadata=token_context_metadata,
    )

    summary = updated_session_summary(
        str(session.get("summary") or ""),
        payload.question,
        payload.filters.model_dump(),
    )
    updated_session = repository.update_chat_session_after_assistant(
        session_id,
        title=title,
        summary=summary,
        model_route=payload.model_route,
        filters=payload.filters.model_dump(),
    )
    return {
        "session": updated_session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "response": response,
    }


def contextual_retrieval_query(question: str, recent_user_context: list[str], session_summary: str) -> str:
    if not should_use_recent_context(question, recent_user_context):
        return question
    context = " ".join([*recent_user_context[-2:], session_summary[:300]]).strip()
    if not context:
        return question
    return f"{question}\n\nContext for resolving references only: {context[:900]}"


def should_use_recent_context(question: str, recent_user_context: list[str]) -> bool:
    if not recent_user_context:
        return False
    normalized = question.lower()
    return any(marker in normalized for marker in FOLLOW_UP_MARKERS) or len(normalized.split()) <= 5


def updated_session_summary(current_summary: str, question: str, filters: dict[str, object]) -> str:
    active_filters = {
        key: value
        for key, value in filters.items()
        if value and value != ["published"] and value != "published"
    }
    topic = question.strip().replace("\n", " ")[:180]
    filter_text = f" Filters: {active_filters}." if active_filters else ""
    addition = f"Latest user intent: {topic}.{filter_text}"
    prefix = current_summary.strip()
    if not prefix:
        return addition[:600]
    return f"{prefix} {addition}"[-600:]


def chat_context_limit(query: str, requested_limit: int) -> int:
    intent = query_intent(query)
    if "taxi_phone" in intent:
        return min(requested_limit, 6)
    if intent & {"alternate_number", "current_trip", "si_lock", "email", "completed_trip"}:
        return min(requested_limit, 8)
    return min(requested_limit, 7)


def filters_with_unit_types(filters: RetrievalFilters, unit_types: set[str]) -> RetrievalFilters:
    return filters.model_copy(update={"unit_types": sorted(unit_types)})


def annotate_result(result: RetrievalResult, role: str, reason: str) -> RetrievalResult:
    metadata = dict(result.metadata or {})
    metadata["chat_source_role"] = role
    metadata["chat_retrieval_reason"] = reason
    return result.model_copy(
        update={
            "metadata": metadata,
            "rank_source": list(dict.fromkeys([*result.rank_source, reason])),
        }
    )


def index_source_role(result: RetrievalResult) -> str:
    unit_type = str(result.metadata.get("unit_type") or result.section)
    if unit_type == "tool_link":
        return "tool_link"
    if unit_type == "quick_action_rule":
        return "action_template"
    return "issue_router"


def source_role(result: RetrievalResult) -> str:
    metadata = result.metadata or {}
    role = str(metadata.get("chat_source_role") or "")
    if role:
        return role
    unit_type = str(metadata.get("unit_type") or result.section)
    if unit_type == "full_sop":
        return "parent_sop"
    if unit_type == "tool_link":
        return "tool_link"
    if unit_type == "quick_action_rule":
        return "action_template"
    if unit_type in INDEX_UNIT_TYPES:
        return "issue_router"
    return "direct_sop"


def rank_chat_results(results: list[RetrievalResult], limit: int) -> list[RetrievalResult]:
    return sorted(
        semantic_dedupe_results(results),
        key=lambda result: (
            SOURCE_ROLE_ORDER.get(source_role(result), 99),
            -chat_adjusted_score(result),
            -float(result.lexical_score or 0),
            -float(result.vector_score or 0),
        ),
    )[:limit]


def dedupe_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    output: list[RetrievalResult] = []
    seen: set[str] = set()
    for result in results:
        if result.chunk_id in seen:
            continue
        seen.add(result.chunk_id)
        output.append(result)
    return output


def semantic_dedupe_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    output: list[RetrievalResult] = []
    for result in dedupe_results(results):
        duplicate_index = semantic_duplicate_index(output, result)
        if duplicate_index is None:
            output.append(result)
            continue
        current = output[duplicate_index]
        if dedupe_preference_score(result) > dedupe_preference_score(current):
            output[duplicate_index] = merge_duplicate_metadata(result, current)
        else:
            output[duplicate_index] = merge_duplicate_metadata(current, result)
    return output


def semantic_duplicate_index(results: list[RetrievalResult], candidate: RetrievalResult) -> int | None:
    candidate_text = semantic_text(candidate)
    if len(candidate_text) < 28:
        return None
    for index, result in enumerate(results):
        if result.document_id != candidate.document_id or result.version_id != candidate.version_id:
            continue
        if source_role(result) != source_role(candidate):
            continue
        existing_text = semantic_text(result)
        if not existing_text:
            continue
        if candidate_text in existing_text or existing_text in candidate_text:
            return index
        similarity = SequenceMatcher(None, existing_text[:1200], candidate_text[:1200]).ratio()
        if similarity >= 0.86:
            return index
    return None


def merge_duplicate_metadata(keeper: RetrievalResult, duplicate: RetrievalResult) -> RetrievalResult:
    metadata = dict(keeper.metadata or {})
    duplicate_ids = list(metadata.get("chat_duplicate_chunk_ids") or [])
    duplicate_ids.append(duplicate.chunk_id)
    metadata["chat_duplicate_chunk_ids"] = list(dict.fromkeys(duplicate_ids))
    metadata["chat_dedupe_status"] = "semantic_duplicates_merged"
    metadata["chat_duplicate_count"] = len(metadata["chat_duplicate_chunk_ids"])
    return keeper.model_copy(update={"metadata": metadata})


def dedupe_preference_score(result: RetrievalResult) -> float:
    metadata = result.metadata or {}
    unit_type = str(metadata.get("unit_type") or result.section)
    unit_score = {
        "policy_rule": 0.08,
        "handling_rule": 0.07,
        "decision_rule": 0.07,
        "exception_rule": 0.07,
        "sla_rule": 0.06,
        "workflow_step": 0.04,
        "operational_note": 0.03,
        "full_sop": 0.01,
    }.get(unit_type, 0.04)
    source_ref_bonus = 0.04 if has_structured_source_ref(metadata) else 0.0
    return chat_adjusted_score(result) + unit_score + source_ref_bonus


def has_structured_source_ref(metadata: dict[str, Any]) -> bool:
    refs = metadata.get("source_refs")
    if not isinstance(refs, list):
        return False
    for ref in refs:
        if isinstance(ref, dict) and (ref.get("row_start") or ref.get("page") or ref.get("bbox")):
            return True
    return False


def semantic_text(result: RetrievalResult) -> str:
    return normalize_for_match(f"{result.heading} {result.content}")


def rerank_stage_results(query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    query_terms = query_intent(query)
    reranked = [annotate_match_metadata(result, query_terms) for result in results]
    return sorted(
        reranked,
        key=lambda result: (
            -chat_adjusted_score(result),
            -float(result.lexical_score or 0),
            -float(result.vector_score or 0),
        ),
    )


def annotate_match_metadata(result: RetrievalResult, query_terms: set[str]) -> RetrievalResult:
    metadata = dict(result.metadata or {})
    candidate_terms = query_intent(candidate_match_text(result))
    boosts: list[str] = []
    penalties: list[str] = []
    boost = 0.0
    penalty = 0.0

    for term in sorted(query_terms & candidate_terms):
        weight = 0.025
        if term in {"alternate_number", "cs_outbound_reflection", "tx_inbound", "completed_trip", "current_trip"}:
            weight = 0.055
        if term in CHANNEL_GROUPS:
            weight = 0.045
        boost += weight
        boosts.append(term)

    query_channels = query_terms & CHANNEL_GROUPS
    candidate_channels = candidate_terms & CHANNEL_GROUPS
    if query_channels and candidate_channels and not (query_channels & candidate_channels):
        penalty += 0.09
        penalties.append("channel_mismatch")

    for term in sorted((candidate_terms & EXCLUSIVE_CONTEXT_GROUPS) - query_terms):
        penalty += 0.07
        penalties.append(f"context_mismatch:{term}")

    if "cs_outbound_reflection" in query_terms and "si_lock" in candidate_terms and "si_lock" not in query_terms:
        penalty += 0.1
        penalties.append("si_lock_not_asked")
    if "tx" in query_terms and "kh" in candidate_terms and "tx" not in candidate_terms:
        penalty += 0.04
        penalties.append("audience_mismatch")

    adjusted_score = max(0.0, float(result.score or 0.0) + boost - penalty)
    metadata["chat_adjusted_score"] = adjusted_score
    metadata["chat_match_boosts"] = boosts
    metadata["chat_match_penalties"] = penalties
    metadata["chat_intent_terms"] = sorted(candidate_terms)
    return result.model_copy(update={"metadata": metadata})


def chat_adjusted_score(result: RetrievalResult) -> float:
    value = (result.metadata or {}).get("chat_adjusted_score")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(result.score or 0.0)


def relation_seed_candidates(results: list[RetrievalResult], context_limit: int) -> list[RetrievalResult]:
    ranked = sorted(
        semantic_dedupe_results(results),
        key=lambda result: (
            SOURCE_ROLE_ORDER.get(source_role(result), 99),
            -chat_adjusted_score(result),
        ),
    )
    return ranked[: max(3, min(context_limit, 6))]


def query_intent(text: str) -> set[str]:
    normalized = normalize_for_match(text)
    return {
        key
        for key, patterns in INTENT_PATTERNS.items()
        if any(normalize_for_match(pattern) in normalized for pattern in patterns)
    }


def candidate_match_text(result: RetrievalResult) -> str:
    metadata = result.metadata or {}
    metadata_bits = [
        metadata.get("audience"),
        metadata.get("channel"),
        metadata.get("case_type"),
        metadata.get("category"),
        metadata.get("vertical"),
        metadata.get("tags"),
        metadata.get("aliases"),
        metadata.get("section_path"),
    ]
    return " ".join([result.heading, result.section, result.content, *[str(bit) for bit in metadata_bits if bit]])


def normalize_for_match(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", without_accents)).strip()


def evidence_confidence(
    question: str,
    context_results: list[RetrievalResult],
    cited_results: list[RetrievalResult],
    model_confidence: float,
    has_unresolved_dependency: bool,
) -> float:
    if not cited_results:
        return 0.0
    cited_terms = set().union(*(query_intent(candidate_match_text(result)) for result in cited_results))
    query_terms = query_intent(question)
    score = 0.42
    if query_terms and query_terms <= cited_terms:
        score += 0.24
    elif query_terms & cited_terms:
        score += 0.14
    if len(cited_results) >= 2:
        score += 0.08
    if any(float(result.lexical_score or 0) >= 2.5 for result in cited_results):
        score += 0.08
    if any(float(result.vector_score or 0) >= 0.45 for result in cited_results):
        score += 0.04
    if is_exact_lookup(question, cited_results):
        score += 0.12
    penalty_count = sum(len((result.metadata or {}).get("chat_match_penalties") or []) for result in cited_results)
    score -= min(0.18, penalty_count * 0.04)
    if has_unresolved_dependency:
        score = min(score, 0.68)
    context_penalty_count = sum(len((result.metadata or {}).get("chat_match_penalties") or []) for result in context_results[:5])
    if context_penalty_count >= 4:
        score = min(score, 0.74)
    if len(cited_results) == 1 and not is_exact_lookup(question, cited_results):
        score = min(score, 0.82)
    if max(float(result.score or 0) for result in cited_results) < 0.22 and not is_exact_lookup(question, cited_results):
        score = min(score, 0.76)
    if model_confidence <= 0.05:
        score = min(score, 0.45)
    return round(max(0.0, min(score, 0.94)), 2)


def is_exact_lookup(question: str, cited_results: list[RetrievalResult]) -> bool:
    normalized = normalize_for_match(question)
    text = normalize_for_match(" ".join(result.content for result in cited_results))
    asks_phone = "so dien thoai" in normalized or "sdt" in normalized or "hotline" in normalized
    has_phone = bool(re.search(r"\b0\d{8,10}\b", text))
    return asks_phone and has_phone


def source_groups(results: list[RetrievalResult]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for role in SOURCE_ROLE_ORDER:
        sources = [result for result in results if source_role(result) == role]
        if sources:
            groups.append(
                {
                    "role": role,
                    "label": SOURCE_GROUP_LABELS.get(role, role),
                    "sources": [source.model_dump() for source in sources],
                }
            )
    return groups


def has_policy_source(results: list[RetrievalResult]) -> bool:
    return any(source_role(result) in POLICY_SOURCE_ROLES for result in results)


def select_chat_model(request: GroundedChatRequest, retrieval: object) -> ChatModelSelection:
    route = "simple" if request.model_route == "auto" else request.model_route
    reason = "auto_route_disabled_simple_default" if request.model_route == "auto" else "manual_route"
    model = model_for_route(route)
    fallback = settings.openrouter_chat_fallback_model or settings.openrouter_chat_complex_model
    return ChatModelSelection(
        route=route,
        model=model,
        reason=reason,
        strict_grounding=route in {"policy", "high_risk", "complex", "google/gemini-3-flash-preview", "anthropic/claude-3.5-haiku"},
        fallback_model=fallback,
    )


def model_for_route(route: str) -> str:
    if route == "google/gemini-2.5-flash":
        return settings.openrouter_chat_gemini_25_flash_model or route
    if route == "google/gemini-3-flash-preview":
        return settings.openrouter_chat_gemini_3_flash_model or route
    if route == "anthropic/claude-3.5-haiku":
        return settings.openrouter_chat_claude_35_haiku_model or route
    if route == "high_risk":
        return settings.openrouter_chat_high_risk_model or settings.openrouter_chat_policy_model or settings.openrouter_chat_model
    if route == "policy":
        return settings.openrouter_chat_policy_model or settings.openrouter_chat_model
    if route == "complex":
        return settings.openrouter_chat_complex_model or settings.openrouter_chat_fallback_model or settings.openrouter_chat_model
    return settings.openrouter_chat_simple_model or settings.openrouter_chat_model


def elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
