from __future__ import annotations

from typing import Any


DEFAULT_KB_COLLECTIONS: tuple[tuple[str, str, str], ...] = (
    ("cs-core-operating-rules", "CS Core Operating Rules", "domain"),
    ("customer-rider-operations", "Customer / Rider Operations", "audience"),
    ("driver-operations", "Driver Operations", "audience"),
    ("merchant-mcu-operations", "Merchant / MCU Operations", "audience"),
    ("cleaner-operations", "Cleaner Operations", "audience"),
    ("payment-refund", "Payment & Refund", "task"),
    ("account-verification", "Account & Verification", "task"),
    ("trip-order-issues", "Trip / Order Issues", "task"),
    ("promotion-voucher", "Promotion / Voucher", "task"),
    ("social-call-email-handling", "Social / Call / Email Handling", "channel"),
    ("tech-bpla-msc-handoff", "Tech / BPLA / MSC Handoff", "owner"),
    ("qa-zt-compliance", "QA / ZT / Compliance", "risk"),
    ("vip-customer-handling", "VIP Customer Handling", "risk"),
    ("tool-directory", "Tool Directory", "tool"),
    ("product-updates", "Product Updates", "domain"),
)


DEFAULT_TAXONOMY_TERMS: tuple[dict[str, Any], ...] = (
    {"term_key": "tx", "term_type": "chat_intent", "display_name": "Tài xế", "aliases": ["tx", "tai xe", "tai xế", "tài xế"], "metadata": {"audience_role": "driver"}},
    {"term_key": "kh", "term_type": "chat_intent", "display_name": "Khách hàng", "aliases": ["kh", "khach hang", "khách hàng"], "metadata": {"audience_role": "customer"}},
    {"term_key": "hotline", "term_type": "chat_intent", "display_name": "Hotline", "aliases": ["hotline", "1900232345"]},
    {"term_key": "chat_social", "term_type": "chat_intent", "display_name": "Chat social", "aliases": ["chat social"]},
    {"term_key": "call_in_app", "term_type": "chat_intent", "display_name": "Call in-app", "aliases": ["call in app", "cia", "non voice", "non-voice", "chat in app"]},
    {"term_key": "mail", "term_type": "chat_intent", "display_name": "Mail", "aliases": ["mail", "email", "ho.tro", "hotro@be.com.vn", "e-mail"], "metadata": {"chat_context_limit": 8}},
    {"term_key": "alternate_number", "term_type": "chat_intent", "display_name": "Alternate number", "aliases": ["so khac", "sdt khac", "goi sang so", "goi ra so", "lien he ra 1 so", "lien he so dien thoai khac"], "metadata": {"chat_signal": "high", "chat_context_limit": 8}},
    {"term_key": "cs_outbound_reflection", "term_type": "chat_intent", "display_name": "CS outbound reflection", "aliases": ["cs goi tx", "cs lien he tx", "xu ly phan anh", "kh phan anh"], "metadata": {"chat_signal": "high", "outbound_reflection": True}},
    {"term_key": "tx_inbound", "term_type": "chat_intent", "display_name": "TX inbound", "aliases": ["tx chu dong", "tx lien he", "tai xe lien he", "goi vao"], "metadata": {"chat_signal": "high"}},
    {"term_key": "si_lock", "term_type": "chat_intent", "display_name": "SI lock", "aliases": ["si", "bi khoa", "tam khoa", "khoa tai khoan"], "metadata": {"lock_sensitive": True, "chat_context_limit": 8}},
    {"term_key": "foreign_customer", "term_type": "chat_intent", "display_name": "Foreign customer", "aliases": ["nuoc ngoai", "ngoai ngu", "tieng anh", "tieng viet"]},
    {"term_key": "betaxi", "term_type": "chat_intent", "display_name": "beTaxi", "aliases": ["betaxi", "be taxi"]},
    {"term_key": "gsm", "term_type": "chat_intent", "display_name": "GSM", "aliases": ["gsm", "xanh sm"]},
    {"term_key": "taxi_phone", "term_type": "chat_intent", "display_name": "Taxi phone", "aliases": ["so dien thoai hang taxi", "hang taxi", "thanh nga", "van xuan", "thang long"], "metadata": {"chat_context_limit": 6}},
    {"term_key": "current_trip", "term_type": "chat_intent", "display_name": "Current trip", "aliases": ["chuyen dang loi", "chuyen can ho tro", "trip hien tai", "don dang loi"], "metadata": {"chat_signal": "high", "chat_context_limit": 8}},
    {"term_key": "completed_trip", "term_type": "chat_intent", "display_name": "Completed trip", "aliases": ["chuyen hoan thanh gan nhat", "trip hoan thanh gan nhat", "khong phai chuyen xe can ho tro"], "metadata": {"chat_signal": "high", "chat_context_limit": 8}},
    {"term_key": "follow_up_reference", "term_type": "follow_up_marker", "display_name": "Follow-up marker", "aliases": ["cái đó", "cai do", "vậy", "vay", "nó", "no", "tiếp", "tiep", "ở trên", "o tren", "trên", "tren", "khác gì", "khac gi", "thì sao", "thi sao", "còn", "con"]},
)


DEFAULT_TAXONOMY_GROUPS: tuple[dict[str, Any], ...] = (
    {"group_key": "channels", "group_type": "channel", "display_name": "Channels", "term_keys": ["hotline", "chat_social", "call_in_app", "mail"]},
    {"group_key": "exclusive_context", "group_type": "exclusive_context", "display_name": "Exclusive contexts", "term_keys": ["si_lock", "foreign_customer", "betaxi", "gsm", "taxi_phone"]},
)


DEFAULT_SHEET_MAPPING_RULES: tuple[dict[str, Any], ...] = (
    {"rule_key": "overal", "pattern": "overal", "match_type": "exact", "sheet_kind": "collection_summary", "collection_slug": "cs-core-operating-rules", "collection_name": "CS Core Operating Rules", "collection_type": "domain", "priority": 10},
    {"rule_key": "quy_dinh_lam_viec_ccu_pcu", "pattern": "quy dinh lam viec ccu pcu", "match_type": "exact", "sheet_kind": "core_sop_index", "collection_slug": "cs-core-operating-rules", "collection_name": "CS Core Operating Rules", "collection_type": "domain", "priority": 20},
    {"rule_key": "quy_dinh_chung", "pattern": "quy dinh chung", "match_type": "exact", "sheet_kind": "general_sop_index", "collection_slug": "cs-core-operating-rules", "collection_name": "CS Core Operating Rules", "collection_type": "domain", "priority": 30},
    {"rule_key": "driver_rider", "pattern": "driver rider", "match_type": "exact", "sheet_kind": "cross_audience_issue_router", "collection_slug": "trip-order-issues", "collection_name": "Trip / Order Issues", "collection_type": "task", "priority": 40},
    {"rule_key": "driver_cleaner", "pattern": "driver cleaner", "match_type": "exact", "sheet_kind": "driver_cleaner_issue_router", "collection_slug": "driver-operations", "collection_name": "Driver Operations", "collection_type": "audience", "priority": 50},
    {"rule_key": "rider", "pattern": "rider", "match_type": "exact", "sheet_kind": "rider_issue_router", "collection_slug": "customer-rider-operations", "collection_name": "Customer / Rider Operations", "collection_type": "audience", "priority": 60},
    {"rule_key": "cleaner", "pattern": "cleaner", "match_type": "exact", "sheet_kind": "cleaner_issue_router", "collection_slug": "cleaner-operations", "collection_name": "Cleaner Operations", "collection_type": "audience", "priority": 70},
    {"rule_key": "mcu", "pattern": "mcu", "match_type": "exact", "sheet_kind": "merchant_issue_router", "collection_slug": "merchant-mcu-operations", "collection_name": "Merchant / MCU Operations", "collection_type": "audience", "priority": 80},
    {"rule_key": "link_lam_viec", "pattern": "link lam viec", "match_type": "exact", "sheet_kind": "tool_directory", "collection_slug": "tool-directory", "collection_name": "Tool Directory", "collection_type": "tool", "priority": 90},
    {"rule_key": "vip", "pattern": "vip", "match_type": "exact", "sheet_kind": "vip_overlay_policy", "collection_slug": "vip-customer-handling", "collection_name": "VIP Customer Handling", "collection_type": "risk", "priority": 100},
    {"rule_key": "tinh_nang_san_pham_moi", "pattern": "tinh nang san pham moi", "match_type": "exact", "sheet_kind": "product_update_index", "collection_slug": "product-updates", "collection_name": "Product Updates", "collection_type": "domain", "priority": 110},
)


DEFAULT_RELATION_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "pattern_key": "requires_follow_policy",
        "pattern": r"(?:thực hiện|thuc hien|áp dụng|ap dung|xử lý|xu ly|hỗ trợ|ho tro)\s+theo\s+(?P<title>(?:quy\s*(?:định|dinh|trình|trinh)|sop|hướng\s*dẫn|huong\s*dan|macro)[^.;\n]{3,180})",
        "relation_type": "requires",
        "relation_source": "explicit_text_reference",
        "priority": 10,
    },
    {
        "pattern_key": "references_policy",
        "pattern": r"(?:theo|xem(?:\s+thêm)?|tham\s*khảo|tham\s*khao)\s+(?P<title>(?:quy\s*(?:định|dinh|trình|trinh)|sop|hướng\s*dẫn|huong\s*dan|macro)[^.;\n]{3,180})",
        "relation_type": "references",
        "relation_source": "explicit_text_reference",
        "priority": 20,
    },
    {
        "pattern_key": "routes_to_team",
        "pattern": r"(?:chuyển|chuyen)\s+(?:case\s+)?(?:cho|đến|den|về|ve|vào|vao)\s+(?P<title>[A-Za-zÀ-ỹ0-9 _./-]{2,90})",
        "relation_type": "routes_to",
        "relation_source": "operational_handoff",
        "priority": 30,
    },
)


DEFAULT_RERANK_RULES: tuple[dict[str, Any], ...] = (
    {"rule_key": "retrieval_metadata_overlap", "scope": "retrieval_intent", "rule_type": "weight", "weight": 0.018, "params": {"cap": 0.12}, "priority": 10},
    {"rule_key": "retrieval_text_overlap", "scope": "retrieval_intent", "rule_type": "weight", "weight": 0.006, "params": {"cap": 0.05}, "priority": 20},
    {"rule_key": "retrieval_action_metadata_bonus", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.025, "params": {}, "priority": 30},
    {"rule_key": "retrieval_index_unit_bonus", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.08, "params": {}, "priority": 40},
    {"rule_key": "retrieval_text_coverage", "scope": "retrieval_intent", "rule_type": "weight", "weight": 0.12, "params": {"cap": 0.18}, "priority": 50},
    {"rule_key": "retrieval_issue_router_coverage", "scope": "retrieval_intent", "rule_type": "weight", "weight": 0.14, "params": {"cap": 0.16}, "priority": 60},
    {"rule_key": "retrieval_exact_phrase", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.18, "params": {}, "priority": 70},
    {"rule_key": "retrieval_sop_reference_metadata", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.04, "params": {}, "priority": 80},
    {"rule_key": "retrieval_prohibition_match", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.28, "params": {}, "priority": 90},
    {"rule_key": "retrieval_prohibition_high_risk_unit", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.08, "params": {}, "priority": 100},
    {"rule_key": "retrieval_security_query_note", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.06, "params": {}, "priority": 110},
    {"rule_key": "retrieval_high_risk_query", "scope": "retrieval_intent", "rule_type": "bonus", "weight": 0.025, "params": {}, "priority": 120},
    {"rule_key": "repository_structural_sheet_phrase", "scope": "repository_structural", "rule_type": "bonus", "weight": 3.0, "params": {}, "priority": 10},
    {"rule_key": "repository_structural_heading_phrase", "scope": "repository_structural", "rule_type": "bonus", "weight": 2.0, "params": {}, "priority": 20},
    {"rule_key": "repository_structural_token_match", "scope": "repository_structural", "rule_type": "weight", "weight": 0.75, "params": {}, "priority": 30},
    {"rule_key": "chat_previous_cited_source", "scope": "chat_stage", "rule_type": "bonus", "weight": 0.28, "params": {}, "priority": 10},
    {"rule_key": "chat_term_match_default", "scope": "chat_stage", "rule_type": "weight", "weight": 0.025, "params": {}, "priority": 20},
    {"rule_key": "chat_term_match_high_signal", "scope": "chat_stage", "rule_type": "weight", "weight": 0.055, "params": {}, "priority": 30},
    {"rule_key": "chat_term_match_channel", "scope": "chat_stage", "rule_type": "weight", "weight": 0.045, "params": {}, "priority": 40},
    {"rule_key": "chat_channel_mismatch_penalty", "scope": "chat_stage", "rule_type": "penalty", "weight": 0.09, "params": {}, "priority": 50},
    {"rule_key": "chat_context_mismatch_penalty", "scope": "chat_stage", "rule_type": "penalty", "weight": 0.07, "params": {}, "priority": 60},
    {"rule_key": "chat_si_lock_not_asked_penalty", "scope": "chat_stage", "rule_type": "penalty", "weight": 0.1, "params": {}, "priority": 70},
    {"rule_key": "chat_audience_mismatch_penalty", "scope": "chat_stage", "rule_type": "penalty", "weight": 0.04, "params": {}, "priority": 80},
)


DEFAULT_DISPLAY_LABELS: dict[str, dict[str, Any]] = {
    "unit_type": {
        "decision_point": {"label": "Điều kiện"},
        "decision_rule": {"label": "Điều kiện"},
        "workflow_step": {"label": "Bước xử lý"},
        "operational_instruction": {"label": "Hướng dẫn"},
        "routing_rule": {"label": "Điều hướng"},
        "policy_rule": {"label": "Quy định"},
        "exception_rule": {"label": "Ngoại lệ"},
        "handling_rule": {"label": "Xử lý"},
        "sla_rule": {"label": "SLA"},
        "escalation_rule": {"label": "Escalation"},
        "case_creation_rule": {"label": "Tạo case"},
        "handoff_rule": {"label": "Handoff"},
        "macro_script": {"label": "Macro"},
        "operational_note": {"label": "Lưu ý"},
        "security_note": {"label": "Bảo mật"},
        "compliance_note": {"label": "Compliance"},
        "warning": {"label": "Cảnh báo"},
        "related_document": {"label": "Tài liệu liên quan"},
        "issue_router_unit": {"label": "Issue router"},
        "quick_action_rule": {"label": "Quick action"},
        "sop_reference": {"label": "SOP reference"},
        "tool_link": {"label": "Tool"},
        "vip_overlay_rule": {"label": "VIP overlay"},
        "product_update_note": {"label": "Product update"},
        "workflow_graph": {"label": "Workflow graph"},
        "full_sop": {"label": "SOP"},
    },
    "source_role": {
        "direct_sop": {"label": "Direct SOP", "sort_order": 0},
        "issue_router": {"label": "Issue router", "sort_order": 1},
        "related_sop": {"label": "Related SOP", "sort_order": 2},
        "action_template": {"label": "Action templates", "sort_order": 3},
        "tool_link": {"label": "Tools", "sort_order": 4},
        "parent_sop": {"label": "Parent SOP", "sort_order": 5},
    },
}
