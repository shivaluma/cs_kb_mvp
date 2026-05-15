from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DocumentStatus = Literal["active", "archived"]
VersionStatus = Literal["draft", "published", "archived"]
PublishState = Literal[
    "draft",
    "publishing",
    "published_indexing_pending",
    "published_indexing_failed",
    "published_ready",
    "archived",
]
RetrievalMode = Literal["lexical", "vector", "hybrid"]
DocumentType = Literal[
    "text_sop",
    "policy_table",
    "policy_rule",
    "workflow_diagram",
    "kb_index_workbook",
    "asset_sop",
    "macro_script",
    "training_material",
    "unknown",
]
ReviewStatus = Literal["needs_review", "reviewed", "approved", "rejected"]
BulkReviewScope = Literal["all", "atomic"]
RelationType = Literal[
    "references",
    "requires",
    "must_follow",
    "routes_to",
    "escalates_to",
    "uses_macro",
    "uses_tool",
    "has_action_template",
    "has_case_reason",
    "exception_of",
    "supersedes",
    "child_of",
    "parent_of",
    "modifies",
    "related_to",
    "possible_conflict",
]
RelationStatus = Literal["suggested", "unresolved", "approved", "rejected", "archived"]
ChatSessionStatus = Literal["active", "archived"]
ChatModelRoute = Literal[
    "auto",
    "simple",
    "policy",
    "high_risk",
    "complex",
    "google/gemini-2.5-flash",
    "google/gemini-3-flash-preview",
    "anthropic/claude-3.5-haiku",
]
ExtractionUnitType = Literal[
    "full_sop",
    "routing_rule",
    "operational_instruction",
    "policy_rule",
    "validation_rule",
    "handling_rule",
    "exception_rule",
    "threshold_rule",
    "macro_table",
    "wording_rule",
    "workflow_overview",
    "workflow_graph",
    "workflow_step",
    "decision_point",
    "decision_rule",
    "sla_rule",
    "escalation_rule",
    "case_creation_rule",
    "handoff_rule",
    "macro_script",
    "operational_note",
    "security_note",
    "compliance_note",
    "compliance_rule",
    "warning",
    "example",
    "related_document",
    "issue_router_unit",
    "quick_action_rule",
    "sop_reference",
    "tool_link",
    "vip_overlay_rule",
    "product_update_note",
    "follow_up_rule",
    "text_section",
    "candidate_section",
    "candidate_rule",
    "candidate_warning",
    "candidate_table_row",
    "candidate_workflow_text",
    "candidate_step",
    "candidate_action",
    "candidate_decision",
    "candidate_annotation",
    "candidate_sla",
    "candidate_audit_rule",
    "candidate_queue_rule",
]
SynonymType = Literal["regular", "one_way", "typo_correction", "placeholder"]
SynonymStatus = Literal["draft", "in_review", "active", "archived", "rejected"]
SuggestionStatus = Literal["pending", "accepted", "rejected", "archived"]


class SOPMetadata(BaseModel):
    audience: list[str] = Field(default_factory=list)
    vertical: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)


class IndexSOPVersionRequest(BaseModel):
    sop_id: str
    version_id: str
    status: str
    title: str
    sections: dict[str, Any]
    metadata: SOPMetadata


class DocumentMetadata(BaseModel):
    audience: list[str] = Field(default_factory=list)
    vertical: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    case_reasons: list[str] = Field(default_factory=list)
    owner_team: str = ""
    source: str = "upload"
    document_type: DocumentType = "unknown"
    source_type: str = "upload"
    review_status: ReviewStatus = "needs_review"
    extraction_confidence: float = 0.0
    extraction_status: str = "pending_review"
    extraction_lifecycle_status: str = "uploaded"
    extraction_error: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)
    ai_error: str | None = None
    publish_blocked: bool = False
    publish_blocked_reason: str = ""
    source_ref_quality: str = "none"
    requires_human_review: bool = True
    effective_from: str = ""
    required_unit_types: list[str] = Field(default_factory=list)
    risk_level: str = ""
    review_frequency: str = ""
    last_reviewed_at: str = ""
    next_review_due: str = ""
    collection_slug: str = ""
    collection_name: str = ""
    collection_type: str = ""
    collection_assignment_status: str = "unassigned"
    collection_source: str = ""
    collection_confidence: float = 0.0
    suggested_collection_slug: str = ""
    suggested_collection_name: str = ""
    suggested_collection_type: str = ""
    suggested_collection_confidence: float = 0.0
    pipeline_job_status: str = ""
    pipeline_current_stage: str = ""
    pipeline_artifacts: list[dict[str, Any]] = Field(default_factory=list)


class SourceRef(BaseModel):
    source_type: str = Field(min_length=1)
    source_file: str = Field(default="", max_length=300)
    sheet: str = ""
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    column_names: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)
    cell_text: str = ""
    heading_path: list[str] = Field(default_factory=list)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    bbox: list[float] = Field(default_factory=list)

    @field_validator("bbox", mode="before")
    @classmethod
    def normalize_bbox(cls, value: Any) -> list[float]:
        if value in (None, "", "null"):
            return []
        if isinstance(value, dict):
            ordered = [value.get(key) for key in ("x", "y", "width", "height")]
            if all(item is not None for item in ordered):
                value = ordered
            else:
                ordered = [value.get(key) for key in ("x1", "y1", "x2", "y2")]
                value = ordered if all(item is not None for item in ordered) else []
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace("[", "").replace("]", "").split(",")]
            value = [part for part in parts if part]
        if isinstance(value, list):
            output: list[float] = []
            for item in value:
                try:
                    output.append(float(item))
                except (TypeError, ValueError):
                    continue
            return output
        return []


class ExtractedUnit(BaseModel):
    unit_type: ExtractionUnitType
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1)
    confidence: float = Field(default=0.72, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_unit_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        raw_unit_type = str(value.get("unit_type") or metadata.get("unit_type") or "").strip()
        normalized_unit_type = normalize_extraction_unit_type(raw_unit_type, value)
        if normalized_unit_type != raw_unit_type:
            metadata = {**metadata, "original_unit_type": raw_unit_type or None}
            value = {**value, "metadata": metadata}
        value["unit_type"] = normalized_unit_type
        if not value.get("source_refs") and isinstance(metadata.get("source_refs"), list):
            value["source_refs"] = metadata["source_refs"]
        return value


class ExtractedUnitsPayload(BaseModel):
    units: list[ExtractedUnit] = Field(min_length=1)


class ExtractionRefinementPayload(BaseModel):
    units: list[ExtractedUnit] = Field(min_length=1)
    refinement_report: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


ALLOWED_EXTRACTION_UNIT_TYPES = set(ExtractionUnitType.__args__)


def normalize_extraction_unit_type(value: str, payload: dict[str, Any]) -> str:
    normalized = normalize_schema_key(value)
    if normalized in ALLOWED_EXTRACTION_UNIT_TYPES:
        return normalized

    text = normalize_schema_text(" ".join([
        value,
        str(payload.get("title") or ""),
        str(payload.get("content") or ""),
        str(payload.get("metadata") or ""),
    ]))
    mapping = {
        "policy": "policy_rule",
        "rule": "policy_rule",
        "business_rule": "policy_rule",
        "rounding_rule": "policy_rule",
        "email_rule": "policy_rule",
        "procedure": "operational_instruction",
        "procedure_step": "operational_instruction",
        "instruction": "operational_instruction",
        "process_step": "workflow_step",
        "step": "workflow_step",
        "note": "operational_note",
        "risk_note": "warning",
        "warning_note": "warning",
        "alert": "warning",
        "compliance": "compliance_rule",
        "compliance_warning": "compliance_rule",
        "wording": "wording_rule",
        "wording_policy": "wording_rule",
        "macro": "macro_script",
        "macro_row": "macro_script",
        "table_macro": "macro_table",
        "exception": "exception_rule",
        "no_apply": "exception_rule",
        "threshold": "threshold_rule",
        "metadata": "text_section",
        "section": "text_section",
    }
    if normalized in mapping:
        return mapping[normalized]
    if "khong ap dung" in text or "exception" in text:
        return "exception_rule"
    if "moc" in text or "threshold" in text:
        return "threshold_rule"
    if any(signal in text for signal in ["che tai", "noi bo", "compliance", "tuan thu"]):
        return "compliance_rule"
    if any(signal in text for signal in ["xin loi", "wording", "cach noi", "mau cau"]):
        return "wording_rule"
    if any(signal in text for signal in ["luu y", "zt", "loi", "warning", "risk"]):
        return "warning"
    if any(signal in text for signal in ["neu", "doi voi", "truong hop", "quy dinh", "policy", "rule"]):
        return "policy_rule"
    return "operational_instruction"


def normalize_schema_key(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", normalize_schema_text(value))).strip("_")


def normalize_schema_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped.replace("đ", "d").replace("Đ", "D").lower()).strip()


WorkflowNodeType = Literal["start", "end", "action", "decision", "annotation", "warning", "relation"]


def normalize_workflow_node_type(value: Any) -> str:
    normalized = normalize_schema_key(str(value or ""))
    mapping = {
        "": "action",
        "task": "action",
        "step": "action",
        "process": "action",
        "workflow_step": "action",
        "candidate_action": "action",
        "decision_point": "decision",
        "candidate_decision": "decision",
        "note": "annotation",
        "script": "annotation",
        "macro_script": "annotation",
        "sla_rule": "annotation",
        "audit_rule": "warning",
        "warning_note": "warning",
        "related_document": "relation",
        "sop_relation": "relation",
    }
    return mapping.get(normalized, normalized if normalized in {"start", "end", "action", "decision", "annotation", "warning", "relation"} else "action")


def workflow_metadata_has_semantic_contradiction(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("is_decision") is False or metadata.get("not_decision") is True:
        return True
    text = normalize_schema_text(
        " ".join(
            str(value)
            for value in metadata.values()
            if isinstance(value, (str, int, float, bool))
        )
    )
    return "not decision" in text or "not a decision" in text


def sanitize_workflow_node_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    sanitized: dict[str, Any] = {}
    removed = False
    for key, value in metadata.items():
        key_text = normalize_schema_text(str(key))
        value_text = normalize_schema_text(str(value)) if isinstance(value, (str, int, float, bool)) else ""
        if key_text in {"not_decision", "is_decision"} or "not decision" in value_text or "not a decision" in value_text:
            removed = True
            continue
        sanitized[key] = value
    if removed:
        sanitized["semantic_contradiction_removed"] = True
    return sanitized


class WorkflowNodeBase(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: WorkflowNodeType
    semantic_node_type: str = ""
    step_code: str = ""
    shape_kind: str = ""
    terminal_state: str = ""
    actor: str = ""
    lane_id: str = ""
    phase: str = ""
    title: str = Field(min_length=1, max_length=240)
    content: str = ""
    question: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    bbox: list[float] = Field(default_factory=list)
    page: int | None = None
    attached_annotations: list[str] = Field(default_factory=list)
    dedupe_status: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_node_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized["type"] = normalize_workflow_node_type(normalized.get("type") or normalized.get("node_type") or normalized.get("semantic_node_type"))
        for key in ("id", "semantic_node_type", "step_code", "shape_kind", "terminal_state", "actor", "lane_id", "phase", "title", "content", "question", "dedupe_status"):
            raw = normalized.get(key)
            normalized[key] = "" if raw in (None, "null") else str(raw)
        normalized["metadata"] = sanitize_workflow_node_metadata(normalized.get("metadata"))
        title = normalized.get("title") or normalized.get("question") or normalized.get("content") or normalized.get("id") or "Workflow node"
        normalized["title"] = str(title)[:240]
        if not normalized.get("id"):
            normalized["id"] = stable_node_id(str(title), 1)
        if not normalized.get("semantic_node_type"):
            normalized["semantic_node_type"] = normalized["type"]
        return normalized


class StartNode(WorkflowNodeBase):
    type: Literal["start"] = "start"


class EndNode(WorkflowNodeBase):
    type: Literal["end"] = "end"


class ActionNode(WorkflowNodeBase):
    type: Literal["action"] = "action"
    content: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def require_action_content(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized = dict(value)
            content = normalized.get("content") or normalized.get("text") or normalized.get("title") or ""
            normalized["content"] = str(content).strip()
            return normalized
        return value


class DecisionNode(WorkflowNodeBase):
    type: Literal["decision"] = "decision"
    question: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def require_decision_question(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized = dict(value)
            question = normalized.get("question") or normalized.get("content") or normalized.get("title") or normalized.get("text") or ""
            normalized["question"] = str(question).strip()
            return normalized
        return value


class AnnotationNode(WorkflowNodeBase):
    type: Literal["annotation"] = "annotation"
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def flag_orphan_annotation(self) -> "AnnotationNode":
        metadata = dict(self.metadata or {})
        if not self.attached_annotations and not metadata.get("attached_to") and not metadata.get("attached_to_node_id"):
            metadata["orphan_annotation"] = True
            self.metadata = metadata
        return self


class WarningNode(AnnotationNode):
    type: Literal["warning"] = "warning"


class RelationNode(WorkflowNodeBase):
    type: Literal["relation"] = "relation"
    content: str = Field(min_length=1)


WorkflowNode = Annotated[
    StartNode | EndNode | ActionNode | DecisionNode | AnnotationNode | WarningNode | RelationNode,
    Field(discriminator="type"),
]


class WorkflowEdge(BaseModel):
    from_node: str = Field(min_length=1, max_length=120)
    to_node: str = Field(min_length=1, max_length=120)
    condition: str = ""
    confidence: float | None = None
    review_status: str = ""
    review_reason: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_edge_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized["from_node"] = str(normalized.get("from_node") or normalized.get("from") or normalized.get("source") or "")
        normalized["to_node"] = str(normalized.get("to_node") or normalized.get("to") or normalized.get("target") or "")
        normalized["condition"] = str(normalized.get("condition") or "next")
        normalized["review_status"] = str(normalized.get("review_status") or "")
        normalized["review_reason"] = str(normalized.get("review_reason") or normalized.get("reason") or "")
        return normalized


class WorkflowAnnotation(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=80)
    attached_to: str = Field(default="", max_length=120)
    attached_to_node_ids: list[str] = Field(default_factory=list)
    title: str = Field(default="", max_length=180)
    content: str = Field(min_length=1)
    risk_level: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_annotation_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        content = normalized.get("content") or normalized.get("text") or normalized.get("note") or normalized.get("description") or normalized.get("title") or ""
        normalized["content"] = str(content)
        normalized["title"] = str(normalized.get("title") or content or "Workflow annotation")[:180]
        normalized["type"] = str(normalized.get("type") or normalized.get("unit_type") or "annotation")
        normalized["id"] = str(normalized.get("id") or stable_node_id(normalized["title"], 1))
        normalized["attached_to"] = str(normalized.get("attached_to") or normalized.get("attached_to_node_id") or "")
        attached_ids = normalized.get("attached_to_node_ids")
        if not isinstance(attached_ids, list):
            attached_ids = [normalized["attached_to"]] if normalized["attached_to"] else []
        normalized["attached_to_node_ids"] = [str(item) for item in attached_ids if str(item)]
        return normalized


class WorkflowUncertainEdge(BaseModel):
    from_node: str = Field(default="", max_length=120)
    to_node: str = Field(default="", max_length=120)
    condition: str = ""
    reason: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_uncertain_edge_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized["from_node"] = str(normalized.get("from_node") or normalized.get("from") or normalized.get("source") or "")
        normalized["to_node"] = str(normalized.get("to_node") or normalized.get("to") or normalized.get("target") or "")
        normalized["condition"] = str(normalized.get("condition") or "next")
        normalized["reason"] = str(normalized.get("reason") or "topology_needs_manual_review")
        return normalized


class WorkflowGraph(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    start_node_id: str = Field(min_length=1, max_length=120)
    lanes: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[WorkflowNode] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    annotations: list[WorkflowAnnotation] = Field(default_factory=list)
    warnings: list[WorkflowAnnotation] = Field(default_factory=list)
    uncertain_edges: list[WorkflowUncertainEdge] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    graph_confidence: float = Field(ge=0, le=1)
    fidelity_score: float | None = None
    visible_step_codes: list[str] = Field(default_factory=list)
    covered_step_codes: list[str] = Field(default_factory=list)
    missing_step_codes: list[str] = Field(default_factory=list)
    detector_conflicts: list[str] = Field(default_factory=list)
    topology_source: str = ""
    topology_review_required: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    graph_fidelity_score: float | None = None
    selected_flow: str = ""
    repair_applied: bool = False
    repair_report: dict[str, Any] = Field(default_factory=dict)
    decision_edges_review_required: int = 0
    missing_terminal_edges: list[str] = Field(default_factory=list)
    orphan_annotations: list[str] = Field(default_factory=list)
    unresolved_relations: list[dict[str, Any]] = Field(default_factory=list)
    requires_human_review: bool = True
    review_reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_graph_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        graph_title = str(value.get("title") or value.get("name") or "Workflow graph").strip()
        value["title"] = graph_title[:240] or "Workflow graph"
        value["workflow_id"] = str(value.get("workflow_id") or stable_node_id(graph_title, 1))
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            normalized_nodes = []
            id_map: dict[str, str] = {}
            for index, node in enumerate(nodes, start=1):
                if not isinstance(node, dict):
                    normalized_nodes.append(node)
                    continue
                original_id = str(node.get("id") or "").strip()
                title = str(node.get("title") or node.get("question") or node.get("content") or f"Bước {index}").strip()
                node_id = original_id or stable_node_id(title, index)
                id_map[original_id or str(index)] = node_id
                id_map[title] = node_id
                node_type = normalize_workflow_node_type(node.get("type") or node.get("node_type") or node.get("semantic_node_type"))
                node_metadata = sanitize_workflow_node_metadata(node.get("metadata"))
                normalized_nodes.append({**node, "id": node_id, "type": node_type, "metadata": node_metadata, "title": title[:240]})
            value["nodes"] = normalized_nodes
            if not value.get("start_node_id") and normalized_nodes and isinstance(normalized_nodes[0], dict):
                value["start_node_id"] = normalized_nodes[0].get("id")

            edges = value.get("edges")
            if isinstance(edges, list):
                normalized_edges = []
                for edge in edges:
                    if not isinstance(edge, dict):
                        normalized_edges.append(edge)
                        continue
                    from_node = edge.get("from_node") or edge.get("from") or edge.get("source")
                    to_node = edge.get("to_node") or edge.get("to") or edge.get("target")
                    normalized_edges.append(
                        {
                            **edge,
                            "from_node": id_map.get(str(from_node), from_node),
                            "to_node": id_map.get(str(to_node), to_node),
                        }
                    )
                value["edges"] = normalized_edges
        value.setdefault("graph_confidence", 0.68)
        value.setdefault("requires_human_review", True)
        return value


class WorkflowExtractionPayload(BaseModel):
    document_metadata: dict[str, Any] = Field(default_factory=dict)
    full_sop: ExtractedUnit
    workflow_graph: WorkflowGraph
    atomic_units: list[ExtractedUnit] = Field(default_factory=list)
    annotations: list[WorkflowAnnotation] = Field(default_factory=list)
    uncertain_edges: list[WorkflowUncertainEdge] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    search_enrichment: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_workflow_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        warnings = list(value.get("warnings") or [])
        validation_errors = list(value.get("validation_errors") or [])
        legacy_units = collect_legacy_units(value)

        if "atomic_units" not in value and legacy_units:
            value["atomic_units"] = [unit for unit in legacy_units if unit.get("unit_type") != "full_sop"]
            warnings.append("legacy_units_mapped_to_atomic_units")

        if not value.get("full_sop"):
            full_sop = next((unit for unit in legacy_units if unit.get("unit_type") == "full_sop"), None)
            if full_sop is None:
                full_sop = synthesize_full_sop_unit(value, legacy_units)
                warnings.append("full_sop_missing_from_model_synthesized_for_review")
            value["full_sop"] = ensure_unit_source_refs(full_sop)

        if not value.get("workflow_graph"):
            workflow_graph = extract_legacy_workflow_graph(value, legacy_units)
            if workflow_graph is None:
                workflow_graph = synthesize_minimal_workflow_graph(value["full_sop"])
                warnings.append("workflow_graph_missing_from_model_synthesized_for_review")
            value["workflow_graph"] = workflow_graph
            warnings.append("legacy_or_missing_workflow_graph_normalized")

        workflow_graph = value.get("workflow_graph") if isinstance(value.get("workflow_graph"), dict) else {}
        if not value.get("annotations") and isinstance(workflow_graph.get("annotations"), list):
            value["annotations"] = workflow_graph.get("annotations")
            warnings.append("workflow_graph_annotations_promoted")
        if not value.get("uncertain_edges") and isinstance(workflow_graph.get("uncertain_edges"), list):
            value["uncertain_edges"] = workflow_graph.get("uncertain_edges")
            warnings.append("workflow_graph_uncertain_edges_promoted")

        value["atomic_units"] = [
            ensure_unit_source_refs(unit)
            for unit in value.get("atomic_units", [])
            if isinstance(unit, dict) and unit.get("content")
        ]
        value["annotations"] = [
            ensure_workflow_annotation(annotation, index)
            for index, annotation in enumerate(value.get("annotations", []), start=1)
            if isinstance(annotation, dict) and (
                annotation.get("content")
                or annotation.get("title")
                or annotation.get("note")
                or annotation.get("text")
                or annotation.get("description")
            )
        ]
        value["warnings"] = list(dict.fromkeys(str(warning) for warning in warnings if warning))
        value["validation_errors"] = list(dict.fromkeys(str(error) for error in validation_errors if error))
        return value


def stable_node_id(title: str, index: int) -> str:
    title = title.replace("Đ", "D").replace("đ", "d")
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_title.lower()).strip("_")
    if not normalized:
        normalized = f"node_{index}"
    return normalized[:90]


def collect_legacy_units(value: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("units", "atomic_units", "extracted_units", "knowledge_units"):
        items = value.get(key)
        if isinstance(items, list):
            candidates.extend(item for item in items if isinstance(item, dict))
    return candidates


def ensure_unit_source_refs(unit: dict[str, Any]) -> dict[str, Any]:
    content = str(unit.get("content") or unit.get("summary") or unit.get("description") or "").strip()
    title = str(unit.get("title") or unit.get("heading") or content[:80] or "Đơn vị workflow cần review").strip()
    unit_type = str(unit.get("unit_type") or "workflow_step").strip()
    if unit_type not in ExtractionUnitType.__args__:
        unit_type = "workflow_step"
    source_refs = unit.get("source_refs")
    metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
    if not source_refs:
        source_refs = metadata.get("source_refs")
    if not source_refs:
        source_refs = [{"source_type": "pdf_diagram", "source_file": "", "page": 1, "bbox": []}]
    return {
        **unit,
        "unit_type": unit_type,
        "title": title[:180],
        "content": content or title,
        "metadata": metadata,
        "source_refs": source_refs,
    }


def ensure_workflow_annotation(annotation: dict[str, Any], index: int) -> dict[str, Any]:
    content = str(
        annotation.get("content")
        or annotation.get("note")
        or annotation.get("text")
        or annotation.get("description")
        or annotation.get("title")
        or ""
    ).strip()
    title = str(annotation.get("title") or content[:80] or f"Ghi chú {index}").strip()
    annotation_type = str(annotation.get("type") or annotation.get("unit_type") or annotation.get("annotation_type") or "operational_note").strip()
    source_refs = annotation.get("source_refs")
    if not source_refs:
        source_refs = annotation.get("metadata", {}).get("source_refs") if isinstance(annotation.get("metadata"), dict) else None
    if not source_refs:
        source_refs = [{"source_type": "pdf_diagram", "source_file": "", "page": 1, "bbox": []}]
    annotation_id = str(annotation.get("id") or stable_node_id(title or annotation_type, index)).strip()
    return {
        **annotation,
        "id": annotation_id[:120],
        "type": annotation_type[:80] or "operational_note",
        "title": title[:180],
        "content": content or title,
        "source_refs": source_refs,
    }


def synthesize_full_sop_unit(value: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = value.get("document_metadata") if isinstance(value.get("document_metadata"), dict) else {}
    title = str(metadata.get("title") or value.get("title") or "Bản nháp SOP workflow cần review")
    content_parts = [
        str(unit.get("content") or unit.get("summary") or "").strip()
        for unit in units[:12]
        if str(unit.get("content") or unit.get("summary") or "").strip()
    ]
    content = "\n".join(content_parts) or "Model không trả full_sop. Backend giữ bản nháp này để CS Ops review lại từ source."
    source_refs = first_source_refs(units) or [{"source_type": "pdf_diagram", "source_file": "", "page": 1, "bbox": []}]
    return {
        "unit_type": "full_sop",
        "title": title,
        "content": content,
        "confidence": min(float_or_default(metadata.get("extraction_confidence"), 0.45), 0.55),
        "metadata": {"retrieval_scope": "document", "source_ref_quality": "page_only"},
        "source_refs": source_refs,
    }


def extract_legacy_workflow_graph(value: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any] | None:
    for key in ("workflow_graph", "workflow", "graph"):
        graph = value.get(key)
        if isinstance(graph, dict):
            return graph

    for unit in units:
        metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
        graph = metadata.get("workflow_graph") or unit.get("workflow_graph")
        if isinstance(graph, dict):
            return graph

    nodes = value.get("nodes")
    edges = value.get("edges")
    if isinstance(nodes, list) and nodes:
        metadata = value.get("document_metadata") if isinstance(value.get("document_metadata"), dict) else {}
        title = str(value.get("title") or metadata.get("title") or "Workflow cần review")
        return {
            "workflow_id": stable_node_id(title, 1),
            "title": title,
            "start_node_id": "",
            "nodes": nodes,
            "edges": edges if isinstance(edges, list) else [],
            "graph_confidence": 0.45,
            "requires_human_review": True,
            "review_reason": "Model trả nodes/edges legacy; cần CS Ops xác nhận topology.",
        }
    return None


def synthesize_minimal_workflow_graph(full_sop: dict[str, Any]) -> dict[str, Any]:
    title = str(full_sop.get("title") or "Workflow cần review")
    node_id = stable_node_id(title, 1)
    source_refs = full_sop.get("source_refs") or [{"source_type": "pdf_diagram", "source_file": "", "page": 1, "bbox": []}]
    return {
        "workflow_id": node_id,
        "title": title,
        "start_node_id": node_id,
        "nodes": [
            {
                "id": node_id,
                "type": "start",
                "title": title,
                "content": "Model không trả workflow_graph. Cần review source diagram và trích lại topology trước khi publish.",
                "source_refs": source_refs,
            }
        ],
        "edges": [],
        "graph_confidence": 0.25,
        "requires_human_review": True,
        "review_reason": "Thiếu workflow_graph từ model; graph tối thiểu chỉ để giữ draft recoverable.",
    }


def first_source_refs(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for unit in units:
        refs = unit.get("source_refs")
        if isinstance(refs, list) and refs:
            return refs
        metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
        refs = metadata.get("source_refs")
        if isinstance(refs, list) and refs:
            return refs
    return []


def float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MetadataSuggestionPayload(BaseModel):
    metadata: DocumentMetadata
    signals: dict[str, Any] = Field(default_factory=dict)


class DocumentVersionResponse(BaseModel):
    document_id: str
    version_id: str
    external_id: str
    title: str
    version_number: int
    status: VersionStatus
    publish_state: PublishState = "draft"
    chunk_count: int
    checksum: str
    document_type: DocumentType = "unknown"
    review_status: ReviewStatus = "needs_review"
    extraction_confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    indexed_at: Optional[datetime] = None
    indexing_error: str = ""
    published_ready_at: Optional[datetime] = None
    warnings: list[str] = Field(default_factory=list)


class BulkReviewVersionRequest(BaseModel):
    actor: str = "system"
    review_status: ReviewStatus = "reviewed"
    scope: BulkReviewScope = "all"
    force: bool = False


class PublishVersionRequest(BaseModel):
    actor: str = "system"
    force: bool = False


class DocumentMetadataPreviewResponse(BaseModel):
    title: str
    suggested_metadata: DocumentMetadata
    document_type: DocumentType = "unknown"
    source_type: str = "upload"
    extraction_confidence: float = 0.0
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class DocumentSummary(BaseModel):
    document_id: str
    external_id: str
    title: str
    source_filename: str
    status: DocumentStatus
    latest_version_id: Optional[str] = None
    latest_version_number: Optional[int] = None
    latest_version_status: Optional[VersionStatus] = None
    latest_publish_state: Optional[PublishState] = None
    latest_document_type: Optional[DocumentType] = None
    latest_review_status: Optional[ReviewStatus] = None
    latest_extraction_confidence: Optional[float] = None
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionSummary(BaseModel):
    version_id: str
    document_id: str
    version_number: int
    status: VersionStatus
    publish_state: PublishState = "draft"
    checksum: str
    chunk_count: int
    document_type: DocumentType = "unknown"
    review_status: ReviewStatus = "needs_review"
    extraction_confidence: float = 0.0
    change_summary: str
    published_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None
    indexing_error: str = ""
    published_ready_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime


class IndexingResultRequest(BaseModel):
    actor: str = "api-gateway"
    success: bool = False
    lexical_index_synced: bool = False
    vector_index_verified: bool = False
    error: str = ""


class DocumentChunkSummary(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    chunk_index: int
    section: str
    heading: str = ""
    content: str
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExtractionStageOutput(BaseModel):
    id: str
    job_id: str
    stage: str
    artifact_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"
    error: str = ""
    created_at: datetime


class ExtractionJobSummary(BaseModel):
    id: str
    document_id: str
    version_id: str
    status: str
    current_stage: str
    source_type: str = ""
    document_type: str = "unknown"
    risk_level: str = ""
    created_at: datetime
    updated_at: datetime
    outputs: list[ExtractionStageOutput] = Field(default_factory=list)


class ExtractionStageInspection(BaseModel):
    stage: str
    output_count: int = 0
    statuses: list[str] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class ExtractionPipelineIssueSummary(BaseModel):
    failed_output_count: int = 0
    degraded_output_count: int = 0
    warning_count: int = 0
    hard_blockers: list[str] = Field(default_factory=list)
    coverage_score: int | None = None


class ExtractionPipelineInspection(BaseModel):
    version_id: str
    document_id: str = ""
    job_id: str = ""
    status: str = "unknown"
    current_stage: str = ""
    source_type: str = ""
    document_type: str = "unknown"
    risk_level: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stage_order: list[str] = Field(default_factory=list)
    stage_summary: list[ExtractionStageInspection] = Field(default_factory=list)
    issue_summary: ExtractionPipelineIssueSummary = Field(default_factory=ExtractionPipelineIssueSummary)
    artifacts: list[ExtractionStageOutput] = Field(default_factory=list)
    summary_markdown: str = ""


class ExtractionUnit(BaseModel):
    unit_id: str
    document_id: str
    version_id: str
    unit_index: int
    unit_type: str
    title: str
    content: str
    source_sheet: str = ""
    source_row: int | None = None
    source_page: int | None = None
    source_bbox: list[float] = Field(default_factory=list)
    confidence: float = 0.0
    review_status: ReviewStatus = "needs_review"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionUnitUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    unit_type: str = Field(min_length=1, max_length=80)
    confidence: float = Field(default=0.75, ge=0, le=1)
    review_status: ReviewStatus = "reviewed"
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor: str = "cs-ops-ui"


class ExtractionUnitCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    unit_type: str = Field(min_length=1, max_length=80)
    confidence: float = Field(default=0.5, ge=0, le=1)
    review_status: ReviewStatus = "needs_review"
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor: str = "cs-ops-ui"


class VersionRawTextResponse(BaseModel):
    version_id: str
    document_id: str
    title: str
    version_number: int
    status: VersionStatus
    raw_text: str
    chunk_count: int
    created_at: datetime


class DocumentRelation(BaseModel):
    id: str
    source_document_id: str
    source_version_id: str
    source_chunk_id: Optional[str] = None
    source_title: str = ""
    target_title: str
    target_document_id: Optional[str] = None
    target_version_id: Optional[str] = None
    target_title_resolved: str = ""
    relation_type: RelationType
    status: RelationStatus
    created_by: str = "system"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AssignRelationRequest(BaseModel):
    target_document_id: str = Field(min_length=1)
    actor: str = "cs-ops-ui"


class CreateRelationRequest(BaseModel):
    source_document_id: str = Field(min_length=1)
    source_version_id: Optional[str] = None
    source_chunk_id: Optional[str] = None
    target_title: str = ""
    target_document_id: Optional[str] = None
    relation_type: RelationType = "references"
    actor: str = "cs-ops-ui"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RejectRelationRequest(BaseModel):
    actor: str = "cs-ops-ui"
    rejection_reason: str = ""


class ArchiveRelationRequest(BaseModel):
    actor: str = "cs-ops-ui"
    archive_reason: str = ""


class RetrievalFilters(BaseModel):
    audience: list[str] = Field(default_factory=list)
    vertical: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_reasons: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    unit_types: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    status: list[VersionStatus] = Field(default_factory=lambda: ["published"])


class SearchFilterOptions(BaseModel):
    audience: list[str] = Field(default_factory=list)
    vertical: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_reasons: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    unit_types: list[str] = Field(default_factory=list)


class KBCollectionSummary(BaseModel):
    id: str
    name: str
    slug: str
    collection_type: str
    description: str = ""
    owner_team: str = ""
    status: str = "active"
    rules: dict[str, Any] = Field(default_factory=dict)
    item_count: int = 0
    high_risk_count: int = 0
    unresolved_relation_count: int = 0
    created_at: datetime
    updated_at: datetime


class KBCollectionDetail(KBCollectionSummary):
    items: list[dict[str, Any]] = Field(default_factory=list)
    issue_router_units: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    action_templates: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class IssueRouterItem(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    issue_text: str = ""
    content: str = ""
    audience: list[str] = Field(default_factory=list)
    vertical: list[str] = Field(default_factory=list)
    case_type: list[str] = Field(default_factory=list)
    task_type: list[str] = Field(default_factory=list)
    collection: str = ""
    target_sop_title: str = ""
    target_sop_id: str | None = None
    tool_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    relation_status: str = ""
    risk_level: str = ""
    review_status: str = ""
    source_ref: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class ToolLinkSummary(BaseModel):
    id: str
    name: str
    url: str
    tool_type: str = "other"
    description: str = ""
    owner_team: str = ""
    status: str = "active"
    used_by: list[dict[str, Any]] = Field(default_factory=list)
    source_document_id: str | None = None
    source_version_id: str | None = None
    source_ref: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ActionTemplateSummary(BaseModel):
    id: str
    name: str
    action_type: str
    description: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    copy_template: str = ""
    related_tool_ids: list[str] = Field(default_factory=list)
    source_unit_id: str | None = None
    status: str = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KBEventRequest(BaseModel):
    action: str = Field(min_length=1, max_length=120)
    entity_type: str = Field(default="kb_index", max_length=120)
    entity_id: str | None = None
    actor: str = "cs-ops-ui"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackQueueItem(BaseModel):
    key: str
    entity_type: str
    entity_id: str
    target_title: str = ""
    source_title: str = ""
    feedback_type: str
    feedback_label: str
    count: int
    last_seen: datetime
    sample_query: str = ""
    sample_comment: str = ""
    suggested_action: str = ""
    severity: str = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsAnalyticsMetric(BaseModel):
    key: str
    label: str
    value: str
    target: str = ""
    detail: str = ""
    tone: str = "default"


class OpsAnalyticsResponse(BaseModel):
    window_days: int
    generated_at: datetime
    events: dict[str, int] = Field(default_factory=dict)
    metrics: list[OpsAnalyticsMetric] = Field(default_factory=list)


class RetrievalRequest(BaseModel):
    query: str
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    limit: int = Field(default=8, ge=1, le=30)
    mode: RetrievalMode = "hybrid"


class Citation(BaseModel):
    document_id: str
    version_id: str
    chunk_id: str
    chunk_index: int
    section: str
    title: str
    version_number: int
    source_filename: str


class RetrievalResult(BaseModel):
    document_id: str
    version_id: str
    chunk_id: str
    title: str
    source_filename: str
    version_number: int
    chunk_index: int
    section: str
    heading: str
    content: str
    score: float
    lexical_score: float
    vector_score: float
    rank_source: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation: Citation


class RetrievalResponse(BaseModel):
    query: str
    normalized_query: str
    query_expansion: dict[str, Any] = Field(default_factory=dict)
    mode: RetrievalMode
    results: list[RetrievalResult]
    citations: list[Citation]
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class GroundedChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str = Field(min_length=1, max_length=4000)
    retrieval_query: str = Field(default="", max_length=4000)
    session_summary: str = Field(default="", max_length=700)
    recent_user_context: list[str] = Field(default_factory=list, max_length=2)
    recent_assistant_context: list[str] = Field(default_factory=list, max_length=1)
    context_chunk_ids: list[str] = Field(default_factory=list, max_length=8)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    limit: int = Field(default=10, ge=1, le=14)
    conversation: list[ChatMessage] = Field(default_factory=list, max_length=8)
    model_route: ChatModelRoute = "simple"

    @field_validator("model_route", mode="before")
    @classmethod
    def default_blank_model_route(cls, value: Any) -> Any:
        return "simple" if value is None or (isinstance(value, str) and not value.strip()) else value


class GroundedAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_indices: list[int] = Field(default_factory=list)


class GroundedChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str
    answer: str
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    sources: list[RetrievalResult] = Field(default_factory=list)
    confidence: float = 0.0
    retrieval: RetrievalResponse
    source_groups: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_trace: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    model_route: str = "auto"
    model_used: str = ""
    model_reason: str = ""


class ChatSessionSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    title: str
    summary: str = ""
    model_route: str = "simple"
    filters: dict[str, Any] = Field(default_factory=dict)
    status: ChatSessionStatus = "active"
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str = ""
    model_route: ChatModelRoute = "simple"
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_route", mode="before")
    @classmethod
    def default_blank_model_route(cls, value: Any) -> Any:
        return "simple" if value is None or (isinstance(value, str) and not value.strip()) else value


class ChatSessionUpdateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = None
    status: Optional[ChatSessionStatus] = None
    model_route: Optional[ChatModelRoute] = None
    filters: Optional[dict[str, Any]] = None

    @field_validator("model_route", mode="before")
    @classmethod
    def ignore_blank_model_route(cls, value: Any) -> Any:
        return None if value is None or (isinstance(value, str) and not value.strip()) else value


class ChatStoredMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    response_payload: dict[str, Any] = Field(default_factory=dict)
    source_chunk_ids: list[str] = Field(default_factory=list)
    token_context_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatSessionMessageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str = Field(min_length=1, max_length=4000)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    limit: int = Field(default=12, ge=1, le=14)
    model_route: ChatModelRoute = "simple"

    @field_validator("model_route", mode="before")
    @classmethod
    def default_blank_model_route(cls, value: Any) -> Any:
        return "simple" if value is None or (isinstance(value, str) and not value.strip()) else value


class ChatSessionMessageResponse(BaseModel):
    session: ChatSessionSummary
    user_message: ChatStoredMessage
    assistant_message: ChatStoredMessage
    response: GroundedChatResponse


class SynonymTerm(BaseModel):
    id: str | None = None
    term: str
    normalized_term: str = ""
    language: str = "vi"


class SynonymGroup(BaseModel):
    id: str
    canonical_key: str
    synonym_type: SynonymType
    domain: str = ""
    audience: str = ""
    status: SynonymStatus
    created_by: str = "system"
    approved_by: str | None = None
    terms: list[SynonymTerm] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SynonymGroupCreateRequest(BaseModel):
    canonical_key: str
    synonym_type: SynonymType = "one_way"
    domain: str = ""
    audience: str = ""
    status: SynonymStatus = "draft"
    terms: list[SynonymTerm | str] = Field(default_factory=list)
    created_by: str = "system"


class SynonymStatusUpdateRequest(BaseModel):
    actor: str = "system"


class SynonymSuggestion(BaseModel):
    id: str
    canonical_key: str = ""
    suggested_terms: list[str] = Field(default_factory=list)
    source: str
    confidence: float
    status: SuggestionStatus
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SynonymSuggestionGenerateRequest(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    min_count: int = Field(default=1, ge=1, le=50)
    limit: int = Field(default=20, ge=1, le=100)


class SynonymSuggestionAcceptRequest(BaseModel):
    canonical_key: str = ""
    synonym_type: SynonymType = "one_way"
    actor: str = "cs-ops"
    submit_review: bool = True


class SemanticSearchRequest(BaseModel):
    query: str
    filters: dict[str, list[str]] = Field(default_factory=dict)
    limit: int = 10


class SuggestRequest(BaseModel):
    query: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class SuggestedSOP(BaseModel):
    sop_id: str
    title: str
    version: int
    confidence: float


class SuggestResponse(BaseModel):
    answer: str
    suggested_sops: list[SuggestedSOP] = Field(default_factory=list)
    citations: list[Citation | dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
