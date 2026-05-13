from __future__ import annotations

import time
from dataclasses import dataclass
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
        confidence = answer.confidence
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

    direct_results = [
        annotate_result(result, "direct_sop", "direct_policy_unit")
        for result in direct_retrieval.results
    ]
    index_results = [
        annotate_result(result, index_source_role(result), "kb_index_match")
        for result in index_retrieval.results
    ]
    initial_results = dedupe_results([*direct_results, *index_results])
    exclude_ids = [result.chunk_id for result in initial_results]
    relation_rows = repository.approved_relation_target_rows_for_chunks(
        [result.chunk_id for result in initial_results],
        [*exclude_ids],
        max(4, request.limit // 2),
    )
    related_results = [
        annotate_result(to_result(row), "related_sop", "approved_relation_expansion")
        for row in relation_rows
    ]
    exclude_ids.extend(result.chunk_id for result in related_results)
    parent_rows = repository.parent_sop_context_rows(
        [result.chunk_id for result in [*direct_results, *related_results]],
        [*exclude_ids],
        max(2, request.limit // 4),
    )
    parent_results = [
        annotate_result(to_result(row), "parent_sop", "parent_full_sop_context")
        for row in parent_rows
    ]
    final_results = rank_chat_results(
        [*direct_results, *index_results, *related_results, *parent_results],
        request.limit,
    )
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
        "direct_count": len(direct_results),
        "index_count": len(index_results),
        "relation_count": len(related_results),
        "parent_count": len(parent_results),
        "final_count": len(final_results),
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
        dedupe_results(results),
        key=lambda result: (
            SOURCE_ROLE_ORDER.get(source_role(result), 99),
            -float(result.score or 0),
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
