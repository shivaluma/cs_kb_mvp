from __future__ import annotations

import time
from dataclasses import dataclass

from app import repository
from app.config import settings
from app.openrouter import generate_grounded_answer
from app.retrieval import retrieve
from app.schemas import GroundedChatRequest, GroundedChatResponse, RetrievalRequest
from app.text_processing import normalize_phrase


@dataclass(frozen=True)
class ChatModelSelection:
    route: str
    model: str
    reason: str
    strict_grounding: bool
    fallback_model: str


HIGH_RISK_TERMS = [
    "refund",
    "hoan tien",
    "boi hoan",
    "compensation",
    "cashback",
    "payment",
    "thanh toan",
    "account",
    "tai khoan",
    "privacy",
    "bao mat",
    "pii",
    "zt",
    "qa cham loi",
    "khong cung cap",
    "order id",
    "trip id",
    "khoa tai khoan",
    "mo khoa",
]
POLICY_TERMS = [
    "neu",
    "thi",
    "truong hop",
    "doi voi",
    "duoc khong",
    "co duoc",
    "khi nao",
    "ngoai le",
    "exception",
    "policy",
    "quy dinh",
    "decision",
    "escalate",
    "chuyen",
    "lead",
]
COMPLEX_TERMS = [
    "tong hop",
    "so sanh",
    "nhieu sop",
    "multi sop",
    "macro",
    "script",
    "soan",
    "viet cau tra loi",
    "polish",
    "rewrite",
    "tom tat",
]


def grounded_chat(request: GroundedChatRequest) -> GroundedChatResponse:
    started_at = time.perf_counter()
    filters = request.filters.model_copy(update={"status": ["published"]})
    retrieval = retrieve(
        RetrievalRequest(
            query=request.question,
            filters=filters,
            limit=request.limit,
            mode="hybrid",
        )
    )

    warnings = [
        "grounded_published_sop_units_only",
        "raw_draft_archived_content_excluded",
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
            latency_ms=elapsed_ms(started_at),
            model_route=selection.route,
            model_used=selection.model,
            model_reason=selection.reason,
        )
        repository.log_chat(response)
        return response

    selection = select_chat_model(request, retrieval)
    answer, answer_warnings = generate_grounded_answer(
        request.question,
        retrieval,
        [message.model_dump() for message in request.conversation],
        model=selection.model,
        strict_grounding=selection.strict_grounding,
    )
    used_model = selection.model
    if answer is None and selection.fallback_model and selection.fallback_model != selection.model:
        fallback_answer, fallback_warnings = generate_grounded_answer(
            request.question,
            retrieval,
            [message.model_dump() for message in request.conversation],
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

    response = GroundedChatResponse(
        question=request.question,
        answer=answer_text,
        steps=steps,
        warnings=[*warnings, *answer.warnings],
        citations=citations,
        sources=cited_results or retrieval.results,
        confidence=confidence,
        retrieval=retrieval,
        latency_ms=elapsed_ms(started_at),
        model_route=selection.route,
        model_used=used_model,
        model_reason=selection.reason,
    )
    repository.log_chat(response)
    return response


def select_chat_model(request: GroundedChatRequest, retrieval: object) -> ChatModelSelection:
    route = request.model_route
    reason = "manual_route" if route != "auto" else "simple_factual_default"
    if route == "auto":
        route, reason = classify_chat_route(request, retrieval)
    model = model_for_route(route)
    fallback = settings.openrouter_chat_fallback_model or settings.openrouter_chat_complex_model
    return ChatModelSelection(
        route=route,
        model=model,
        reason=reason,
        strict_grounding=route in {"policy", "high_risk", "complex"},
        fallback_model=fallback,
    )


def classify_chat_route(request: GroundedChatRequest, retrieval: object) -> tuple[str, str]:
    question = normalize_phrase(request.question)
    source_text = retrieval_signal_text(retrieval)
    combined = f"{question} {source_text}"
    if contains_any(combined, HIGH_RISK_TERMS):
        return "high_risk", "high_risk_terms_in_question_or_sources"
    if contains_any(question, COMPLEX_TERMS) or (contains_any(question, ["tong hop", "so sanh", "macro", "script"]) and len(getattr(retrieval, "results", []) or []) > 1):
        return "complex", "complex_synthesis_or_macro_request"
    if contains_any(question, POLICY_TERMS) or contains_any(source_text, ["policy_rule", "decision_point", "decision_rule", "exception"]):
        return "policy", "policy_decision_exception_terms"
    return "simple", "simple_factual_sop_qa"


def model_for_route(route: str) -> str:
    if route == "high_risk":
        return settings.openrouter_chat_high_risk_model or settings.openrouter_chat_policy_model or settings.openrouter_chat_model
    if route == "policy":
        return settings.openrouter_chat_policy_model or settings.openrouter_chat_model
    if route == "complex":
        return settings.openrouter_chat_complex_model or settings.openrouter_chat_fallback_model or settings.openrouter_chat_model
    return settings.openrouter_chat_simple_model or settings.openrouter_chat_model


def retrieval_signal_text(retrieval: object) -> str:
    parts: list[str] = []
    for result in getattr(retrieval, "results", []) or []:
        metadata = getattr(result, "metadata", {}) or {}
        parts.extend(
            [
                str(getattr(result, "title", "")),
                str(getattr(result, "heading", "")),
                str(getattr(result, "section", "")),
                str(metadata.get("unit_type", "")),
                str(metadata.get("risk_level", "")),
                " ".join(str(item) for item in metadata.get("tags", []) if item),
                str(getattr(result, "content", ""))[:500],
            ]
        )
    return normalize_phrase(" ".join(parts))


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
