from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


DocumentStatus = Literal["active", "archived"]
VersionStatus = Literal["draft", "published", "archived"]
RetrievalMode = Literal["lexical", "vector", "hybrid"]
DocumentType = Literal[
    "text_sop",
    "policy_table",
    "policy_rule",
    "workflow_diagram",
    "asset_sop",
    "macro_script",
    "training_material",
    "unknown",
]
ReviewStatus = Literal["needs_review", "reviewed", "approved"]
ExtractionUnitType = Literal[
    "full_sop",
    "routing_rule",
    "operational_instruction",
    "policy_rule",
    "validation_rule",
    "handling_rule",
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
    "warning",
    "related_document",
    "follow_up_rule",
    "text_section",
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
    extraction_error: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    source_type: str = Field(min_length=1)
    source_file: str = Field(default="", max_length=300)
    sheet: str = ""
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    column_names: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
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


class ExtractedUnitsPayload(BaseModel):
    units: list[ExtractedUnit] = Field(min_length=1)


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=60)
    actor: str = ""
    phase: str = ""
    title: str = Field(min_length=1, max_length=240)
    content: str = ""
    question: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class WorkflowEdge(BaseModel):
    from_node: str = Field(min_length=1, max_length=120)
    to_node: str = Field(min_length=1, max_length=120)
    condition: str = ""


class WorkflowAnnotation(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=80)
    attached_to: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=180)
    content: str = Field(min_length=1)
    risk_level: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class WorkflowUncertainEdge(BaseModel):
    from_node: str = Field(default="", max_length=120)
    to_node: str = Field(default="", max_length=120)
    condition: str = ""
    reason: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_refs: list[SourceRef] = Field(default_factory=list)


class WorkflowGraph(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    start_node_id: str = Field(min_length=1, max_length=120)
    nodes: list[WorkflowNode] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    graph_confidence: float = Field(ge=0, le=1)
    requires_human_review: bool = True
    review_reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_graph_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
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
                normalized_nodes.append({**node, "id": node_id, "title": title})
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


def stable_node_id(title: str, index: int) -> str:
    title = title.replace("Đ", "D").replace("đ", "d")
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_title.lower()).strip("_")
    if not normalized:
        normalized = f"node_{index}"
    return normalized[:90]


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
    chunk_count: int
    checksum: str
    document_type: DocumentType = "unknown"
    review_status: ReviewStatus = "needs_review"
    extraction_confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


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
    checksum: str
    chunk_count: int
    document_type: DocumentType = "unknown"
    review_status: ReviewStatus = "needs_review"
    extraction_confidence: float = 0.0
    change_summary: str
    published_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime


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


class VersionRawTextResponse(BaseModel):
    version_id: str
    document_id: str
    title: str
    version_number: int
    status: VersionStatus
    raw_text: str
    chunk_count: int
    created_at: datetime


class RetrievalFilters(BaseModel):
    audience: list[str] = Field(default_factory=list)
    vertical: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_reasons: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    status: list[VersionStatus] = Field(default_factory=lambda: ["published"])


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
    question: str = Field(min_length=1, max_length=4000)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    limit: int = Field(default=6, ge=1, le=10)
    conversation: list[ChatMessage] = Field(default_factory=list, max_length=8)


class GroundedAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_indices: list[int] = Field(default_factory=list)


class GroundedChatResponse(BaseModel):
    question: str
    answer: str
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    sources: list[RetrievalResult] = Field(default_factory=list)
    confidence: float = 0.0
    retrieval: RetrievalResponse
    latency_ms: int


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
