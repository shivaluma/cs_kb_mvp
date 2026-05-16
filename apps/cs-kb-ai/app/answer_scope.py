from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any


PatternMap = dict[str, tuple[str, ...]]


ASKED_FIELD_PATTERNS: PatternMap = {
    "contact_channel": (
        "kenh nao",
        "qua kenh",
        "kenh lien he",
        "lien he qua",
        "lien lac qua",
        "goi hay mail",
        "call hay mail",
        "email hay call",
        "call out hay email",
    ),
    "info_collection": (
        "khai thac them thong tin",
        "lay them thong tin",
        "xin them thong tin",
        "thu thap them thong tin",
        "xac minh them thong tin",
    ),
    "retry_policy": (
        "goi may lan",
        "bao nhieu lan",
        "toi thieu may lan",
        "cach nhau bao lau",
        "goi lai",
        "lien he lai",
        "retry",
    ),
    "full_workflow": (
        "xu ly nhu the nao",
        "xu ly sao",
        "quy trinh",
        "cac buoc",
        "lam gi tiep",
        "sau do",
        "tiep theo",
    ),
}


EXPLICIT_CONDITION_PATTERNS: PatternMap = {
    "rating_1_star": (
        "rating 1 sao",
        "danh gia 1 sao",
        "1 sao",
    ),
    "driver_attitude_complaint": (
        "complain thai do tx",
        "phan anh thai do tx",
        "khieu nai thai do tx",
        "thai do tai xe",
        "thai do tx",
    ),
    "customer_complaint": (
        "kh complain",
        "kh phan anh",
        "kh khieu nai",
        "khach hang phan anh",
    ),
    "email_missing": (
        "khong co email",
        "chua co email",
        "khong co mail",
        "chua co mail",
        "thieu email",
    ),
    "failed_contact": (
        "khong lien he duoc",
        "kh khong nghe may",
        "khong bat may",
        "khong nghe dien thoai",
        "call khong duoc",
    ),
}


BRANCH_PATTERNS: PatternMap = {
    "email_missing": EXPLICIT_CONDITION_PATTERNS["email_missing"],
    "email_collection": (
        "xin email",
        "cap nhat email",
        "bo sung email",
        "lay email",
        "thu thap email",
    ),
    "retry_policy": (
        "toi thieu 2 lan",
        "toi thieu hai lan",
        "cach nhau 10 phut",
        "goi lai",
        "lien he lai",
        "retry",
        "so lan goi",
    ),
    "failed_contact": EXPLICIT_CONDITION_PATTERNS["failed_contact"],
    "escalation": (
        "escalate",
        "chuyen lead",
        "chuyen bpla",
        "chuyen tech",
        "chuyen qa",
        "chuyen case",
    ),
    "compensation": (
        "boi hoan",
        "hoan tien",
        "refund",
        "compensation",
        "ma voucher",
        "voucher",
    ),
    "sla": (
        "sla",
        "thoi han",
        "trong vong",
        "ngay lam viec",
    ),
    "case_creation": (
        "tao case",
        "case reason",
        "ticket",
        "tasklist",
    ),
}


CONTACT_SCOPE_EXCLUSIONS = frozenset(
    {
        "email_missing",
        "email_collection",
        "retry_policy",
        "failed_contact",
        "escalation",
        "compensation",
        "sla",
        "case_creation",
    }
)


@dataclass(frozen=True)
class AnswerScope:
    asked_fields: tuple[str, ...]
    explicit_conditions: tuple[str, ...]
    excluded_branch_types: tuple[str, ...]
    is_narrow: bool

    def model_dump(self) -> dict[str, Any]:
        return {
            "asked_fields": list(self.asked_fields),
            "explicit_conditions": list(self.explicit_conditions),
            "excluded_branch_types": list(self.excluded_branch_types),
            "is_narrow": self.is_narrow,
            "policy": (
                "Answer only the requested procedural field. Treat excluded_branch_types as "
                "supported-but-out-of-scope unless the question explicitly asks for them."
            ),
        }


def build_answer_scope(question: str) -> AnswerScope:
    asked_fields = detect_pattern_keys(question, ASKED_FIELD_PATTERNS)
    explicit_conditions = detect_pattern_keys(question, EXPLICIT_CONDITION_PATTERNS)
    branch_mentions = detect_pattern_keys(question, BRANCH_PATTERNS)

    exclusions: set[str] = set()
    if "contact_channel" in asked_fields:
        exclusions.update(CONTACT_SCOPE_EXCLUSIONS)
    if "retry_policy" in asked_fields:
        exclusions.discard("retry_policy")
        exclusions.discard("failed_contact")
    exclusions.difference_update(explicit_conditions)
    exclusions.difference_update(branch_mentions)

    is_narrow = "contact_channel" in asked_fields and "full_workflow" not in asked_fields
    return AnswerScope(
        asked_fields=tuple(sorted(asked_fields)),
        explicit_conditions=tuple(sorted(explicit_conditions)),
        excluded_branch_types=tuple(sorted(exclusions)),
        is_narrow=is_narrow,
    )


def source_scope_metadata(text: str, scope: AnswerScope) -> dict[str, Any]:
    branch_terms = detect_pattern_keys(text, BRANCH_PATTERNS)
    unasked = sorted(branch_terms & set(scope.excluded_branch_types))
    return {
        "chat_scope_branch_terms": sorted(branch_terms),
        "chat_scope_unasked_branches": unasked,
        "chat_scope_asked_fields": list(scope.asked_fields),
        "chat_scope_narrow": scope.is_narrow,
    }


def scope_penalty(text: str, scope: AnswerScope) -> tuple[float, list[str], dict[str, Any]]:
    metadata = source_scope_metadata(text, scope)
    unasked = metadata["chat_scope_unasked_branches"]
    if not unasked:
        return 0.0, [], metadata
    penalty = min(0.36, 0.12 * len(unasked))
    return penalty, [f"unasked_branch:{branch}" for branch in unasked], metadata


def prune_answer_to_scope(answer: str, steps: list[str], question: str) -> tuple[str, list[str], list[str]]:
    scope = build_answer_scope(question)
    if not scope.excluded_branch_types:
        return answer, steps, []

    pruned_answer, answer_removed = remove_unasked_segments(answer, scope)
    pruned_steps: list[str] = []
    step_removed: set[str] = set()
    for step in steps:
        branch_terms = detect_pattern_keys(step, BRANCH_PATTERNS) & set(scope.excluded_branch_types)
        if branch_terms:
            step_removed.update(branch_terms)
            continue
        pruned_steps.append(step)

    removed = sorted(set(answer_removed) | step_removed)
    warnings = [f"out_of_scope_branch_claim_removed:{branch}" for branch in removed]
    return pruned_answer, pruned_steps, warnings


def remove_unasked_segments(answer: str, scope: AnswerScope) -> tuple[str, list[str]]:
    segments = split_answer_segments(answer)
    if len(segments) <= 1:
        branch_terms = detect_pattern_keys(answer, BRANCH_PATTERNS) & set(scope.excluded_branch_types)
        return answer, sorted(branch_terms)

    kept: list[str] = []
    removed: set[str] = set()
    for segment in segments:
        branch_terms = detect_pattern_keys(segment, BRANCH_PATTERNS) & set(scope.excluded_branch_types)
        if branch_terms:
            removed.update(branch_terms)
            continue
        kept.append(segment.strip())

    if not kept:
        return answer, sorted(removed)
    return " ".join(kept).strip(), sorted(removed)


def split_answer_segments(answer: str) -> list[str]:
    text = str(answer or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+|;\s+", text)
    output: list[str] = []
    for part in parts:
        subparts = re.split(r"(?=\b(?:nếu|neu|trường hợp|truong hop|đối với|doi voi|khi)\b)", part, flags=re.IGNORECASE)
        output.extend(subpart.strip() for subpart in subparts if subpart.strip())
    return output


def detect_pattern_keys(text: str, patterns: PatternMap) -> set[str]:
    normalized = normalize_operational_text(text)
    return {
        key
        for key, values in patterns.items()
        if any(normalize_operational_text(pattern) in normalized for pattern in values)
    }


def normalize_operational_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", without_accents)).strip()
