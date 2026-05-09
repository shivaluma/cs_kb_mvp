from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


DocumentStatus = Literal["active", "archived"]
VersionStatus = Literal["draft", "published", "archived"]
RetrievalMode = Literal["lexical", "vector", "hybrid"]
DocumentType = Literal[
    "text_sop",
    "policy_table",
    "workflow_diagram",
    "asset_sop",
    "macro_script",
    "training_material",
    "unknown",
]
ReviewStatus = Literal["needs_review", "reviewed", "approved"]
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
