from __future__ import annotations

import re
import unicodedata
from typing import Any


STEP_CODE_ONLY_RE = re.compile(r"^\s*(?:bước\s*)?\d{1,3}(?:\.\d{1,3})*\.?\s*$", re.IGNORECASE)
LEADING_STEP_RE = re.compile(r"^\s*(?:bước\s*)?(\d{1,3}(?:\.\d{1,3})*)[.)]?\s*", re.IGNORECASE)
BAD_LABELS = {"", "yes", "no", "start", "end", "row", "dong", "dòng", "link", "na", "n/a"}

UNIT_TYPE_LABELS = {
    "decision_point": "Điều kiện",
    "decision_rule": "Điều kiện",
    "workflow_step": "Bước xử lý",
    "operational_instruction": "Hướng dẫn",
    "routing_rule": "Điều hướng",
    "policy_rule": "Quy định",
    "exception_rule": "Ngoại lệ",
    "handling_rule": "Xử lý",
    "sla_rule": "SLA",
    "escalation_rule": "Escalation",
    "case_creation_rule": "Tạo case",
    "handoff_rule": "Handoff",
    "macro_script": "Macro",
    "operational_note": "Lưu ý",
    "security_note": "Bảo mật",
    "compliance_note": "Compliance",
    "warning": "Cảnh báo",
    "related_document": "Tài liệu liên quan",
    "issue_router_unit": "Issue router",
    "quick_action_rule": "Quick action",
    "sop_reference": "SOP reference",
    "tool_link": "Tool",
    "vip_overlay_rule": "VIP overlay",
    "product_update_note": "Product update",
    "workflow_graph": "Workflow graph",
    "full_sop": "Document overview",
    "source_evidence_section": "Source evidence",
}


def normalize_label_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9?]+", " ", stripped)).strip()


def normalize_display_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_bad_search_label(label: Any, content: Any = "") -> bool:
    clean_label = normalize_display_text(label)
    if not clean_label:
        return True
    normalized_label = normalize_label_text(clean_label)
    normalized_content = normalize_label_text(str(content or ""))
    if normalized_label in BAD_LABELS:
        return True
    if STEP_CODE_ONLY_RE.match(clean_label):
        return True
    if len(normalized_label) <= 1:
        return True
    if len(clean_label) > 110:
        return True
    if re.search(r"\s[-/]\s", clean_label) and len(clean_label) <= 90:
        return False
    if normalized_content and len(normalized_label) >= 8:
        if normalized_content.startswith(normalized_label):
            return True
        if normalized_label in normalized_content[:180] and label_overlap_ratio(normalized_label, normalized_content) >= 0.72:
            return True
    return False


def meaningful_search_label(label: Any, content: Any, unit_type: str = "") -> str:
    clean_label = normalize_display_text(label)
    clean_content = normalize_display_text(content)
    if not is_bad_search_label(clean_label, clean_content):
        return clean_label[:180]
    return generated_search_label(clean_content, unit_type)[:180]


def embedding_text_for_unit(label: Any, content: Any, unit_type: str = "") -> str:
    clean_content = normalize_display_text(content)
    label_text = meaningful_search_label(label, clean_content, unit_type)
    if not clean_content:
        return label_text
    if is_bad_search_label(label, clean_content):
        return " ".join(part for part in [label_text, clean_content] if part)
    return " ".join([label_text, clean_content])


def generated_search_label(content: str, unit_type: str = "") -> str:
    clean_content = normalize_display_text(content)
    prefix = UNIT_TYPE_LABELS.get(unit_type, readable_unit_type(unit_type))
    if not clean_content:
        return prefix or "Search label"
    step_code, body = split_leading_step(clean_content)
    body = trim_sentence(body or clean_content)
    body = trim_words(body, 10)
    if step_code and body:
        if unit_type in {"decision_point", "decision_rule"} or body.endswith("?"):
            return f"Điều kiện {step_code}: {body}"
        return f"Bước {step_code}: {body}"
    if prefix and body and not normalize_label_text(body).startswith(normalize_label_text(prefix)):
        return f"{prefix}: {body}"
    return body or prefix or "Search label"


def split_leading_step(content: str) -> tuple[str, str]:
    match = LEADING_STEP_RE.match(content)
    if not match:
        return "", content
    return match.group(1), content[match.end():].strip()


def trim_sentence(value: str) -> str:
    text = normalize_display_text(value)
    sentence = re.split(r"[.;\n]", text, maxsplit=1)[0].strip()
    return sentence or text


def trim_words(value: str, limit: int) -> str:
    words = normalize_display_text(value).split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit])


def readable_unit_type(unit_type: str) -> str:
    text = str(unit_type or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Search label"


def label_overlap_ratio(label: str, content: str) -> float:
    label_tokens = [token for token in label.split() if token]
    content_tokens = set(token for token in content.split()[:32] if token)
    if not label_tokens:
        return 0.0
    return sum(1 for token in label_tokens if token in content_tokens) / len(label_tokens)
