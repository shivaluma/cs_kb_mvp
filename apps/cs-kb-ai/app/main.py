from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app import repository
from app.ingestion import prepare_document_version
from app.retrieval import retrieve
from app.schemas import (
    DocumentMetadata,
    DocumentSummary,
    DocumentVersionResponse,
    IndexSOPVersionRequest,
    RetrievalFilters,
    RetrievalRequest,
    RetrievalResponse,
    SemanticSearchRequest,
    SuggestRequest,
    SuggestResponse,
    SuggestedSOP,
    SynonymGroup,
    SynonymGroupCreateRequest,
    SynonymStatusUpdateRequest,
    SynonymSuggestion,
    SynonymSuggestionAcceptRequest,
    SynonymSuggestionGenerateRequest,
    VersionSummary,
)
from app.text_processing import expand_query


app = FastAPI(title="CS KB AI Service", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    repository.ensure_schema()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "cs-kb-ai", "retrieval_store": "postgres_pgvector"}


@app.post("/ai/v1/documents/upload", response_model=DocumentVersionResponse)
async def upload_document(
    file: UploadFile = File(...),
    external_id: str = Form(""),
    title: str = Form(""),
    status: str = Form("published"),
    metadata: str = Form("{}"),
    created_by: str = Form("system"),
    change_summary: str = Form(""),
) -> DocumentVersionResponse:
    if status not in {"draft", "published"}:
        raise HTTPException(status_code=400, detail="status_must_be_draft_or_published")

    parsed_metadata = parse_metadata(metadata)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")

    raw_text, digest, chunks, warnings = prepare_document_version(
        filename=file.filename or "document.txt",
        content_type=file.content_type or "text/plain",
        data=data,
        metadata=parsed_metadata,
    )
    if not chunks:
        raise HTTPException(status_code=400, detail={"error": "no_chunks_created", "warnings": warnings})

    version = repository.create_document_version(
        external_id=external_id or digest,
        title=title or file.filename or digest,
        source_filename=file.filename or "document.txt",
        content_type=file.content_type or "text/plain",
        checksum=digest,
        raw_text=raw_text,
        chunks=chunks,
        metadata=parsed_metadata,
        status=status,
        created_by=created_by,
        change_summary=change_summary,
    )
    return DocumentVersionResponse(**version, warnings=warnings)


@app.get("/ai/v1/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return [DocumentSummary(**row) for row in repository.list_documents()]


@app.get("/ai/v1/documents/{document_id}/versions", response_model=list[VersionSummary])
def list_document_versions(document_id: str) -> list[VersionSummary]:
    return [VersionSummary(**row) for row in repository.list_versions(document_id)]


@app.post("/ai/v1/versions/{version_id}/publish")
def publish_version(version_id: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        return repository.publish_version(version_id, (payload or {}).get("actor", "system"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/ai/v1/documents/{document_id}/archive")
def archive_document(document_id: str, payload: dict[str, str] | None = None) -> dict[str, str]:
    try:
        repository.archive_document(document_id, (payload or {}).get("actor", "system"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"archived": "true", "document_id": document_id}


@app.post("/ai/v1/retrieve", response_model=RetrievalResponse)
def retrieve_documents(request: RetrievalRequest) -> RetrievalResponse:
    return retrieve(request)


@app.get("/ai/v1/search/taxonomy/intents")
def list_taxonomy_intents(status: str = "active") -> list[dict[str, Any]]:
    return repository.list_taxonomy_intents(status)


@app.get("/ai/v1/search/synonyms", response_model=list[SynonymGroup])
def list_synonyms(status: str = "") -> list[SynonymGroup]:
    return [SynonymGroup(**row) for row in repository.list_synonym_groups(status)]


@app.get("/ai/v1/search/synonyms/active", response_model=list[SynonymGroup])
def list_active_synonyms() -> list[SynonymGroup]:
    return [SynonymGroup(**row) for row in repository.active_synonym_groups()]


@app.post("/ai/v1/search/synonyms", response_model=SynonymGroup)
def create_synonym_group(request: SynonymGroupCreateRequest) -> SynonymGroup:
    return SynonymGroup(**repository.create_synonym_group(request))


@app.post("/ai/v1/search/synonyms/{group_id}/submit-review", response_model=SynonymGroup)
def submit_synonym_review(group_id: str, payload: SynonymStatusUpdateRequest | None = None) -> SynonymGroup:
    try:
        return SynonymGroup(**repository.update_synonym_status(group_id, "in_review", (payload or SynonymStatusUpdateRequest()).actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/ai/v1/search/synonyms/{group_id}/approve", response_model=SynonymGroup)
def approve_synonym_group(group_id: str, payload: SynonymStatusUpdateRequest | None = None) -> SynonymGroup:
    try:
        return SynonymGroup(**repository.update_synonym_status(group_id, "active", (payload or SynonymStatusUpdateRequest()).actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/ai/v1/search/synonyms/{group_id}/archive", response_model=SynonymGroup)
def archive_synonym_group(group_id: str, payload: SynonymStatusUpdateRequest | None = None) -> SynonymGroup:
    try:
        return SynonymGroup(**repository.update_synonym_status(group_id, "archived", (payload or SynonymStatusUpdateRequest()).actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ai/v1/search/synonyms/meilisearch")
def meilisearch_synonyms_payload() -> dict[str, list[str]]:
    return repository.meilisearch_synonyms_payload()


@app.post("/ai/v1/search/synonym-suggestions/generate", response_model=list[SynonymSuggestion])
def generate_synonym_suggestions(request: SynonymSuggestionGenerateRequest) -> list[SynonymSuggestion]:
    return [SynonymSuggestion(**row) for row in repository.generate_synonym_suggestions(request.days, request.min_count, request.limit)]


@app.get("/ai/v1/search/synonym-suggestions", response_model=list[SynonymSuggestion])
def list_synonym_suggestions(status: str = "pending", limit: int = 50) -> list[SynonymSuggestion]:
    return [SynonymSuggestion(**row) for row in repository.list_synonym_suggestions(status, limit)]


@app.post("/ai/v1/search/synonym-suggestions/{suggestion_id}/accept", response_model=SynonymGroup)
def accept_synonym_suggestion(suggestion_id: str, request: SynonymSuggestionAcceptRequest) -> SynonymGroup:
    try:
        return SynonymGroup(**repository.accept_synonym_suggestion(suggestion_id, request))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ai/v1/search/semantic")
def semantic_search(request: SemanticSearchRequest) -> dict[str, Any]:
    filters = RetrievalFilters(**request.filters)
    response = retrieve(RetrievalRequest(query=request.query, filters=filters, limit=request.limit, mode="vector"))
    return response.model_dump()


@app.post("/ai/v1/index/sop-version")
def index_sop_version(request: IndexSOPVersionRequest) -> dict[str, Any]:
    if request.status != "published":
        return {
            "indexed": False,
            "reason": "only_published_versions_are_indexed",
            "sop_id": request.sop_id,
            "version_id": request.version_id,
        }

    raw_text = "\n".join(section_to_text(value) for value in request.sections.values())
    data = raw_text.encode("utf-8")
    metadata = DocumentMetadata(
        audience=request.metadata.audience,
        vertical=request.metadata.vertical,
        category=request.metadata.category,
        tags=request.metadata.tags,
        source="sop_version",
    )
    _, digest, chunks, warnings = prepare_document_version(
        filename=f"{request.sop_id}-{request.version_id}.txt",
        content_type="text/plain",
        data=data,
        metadata=metadata,
    )
    version = repository.create_document_version(
        external_id=f"sop:{request.sop_id}",
        title=request.title,
        source_filename=f"{request.sop_id}.txt",
        content_type="text/plain",
        checksum=digest,
        raw_text=raw_text,
        chunks=chunks,
        metadata=metadata,
        status="published",
        created_by="api",
        change_summary=f"Indexed SOP version {request.version_id}",
    )
    return {"indexed": True, **version, "warnings": warnings}


@app.post("/ai/v1/delete/sop-version")
def delete_sop_version(payload: dict[str, str]) -> dict[str, Any]:
    # SOP delete is represented as document archive in this MVP when external_id maps to sop:<sop_id>.
    return {"deleted": False, "reason": "use_archive_document", "sop_id": payload.get("sop_id", "")}


@app.post("/ai/v1/suggest", response_model=SuggestResponse)
def suggest(request: SuggestRequest) -> SuggestResponse:
    retrieval = retrieve(RetrievalRequest(query=request.query, limit=3, mode="hybrid"))
    if not retrieval.results:
        return SuggestResponse(
            answer="Khong tim thay document/SOP published du tin cay de tra loi.",
            warnings=["no_reliable_source"],
        )

    top = retrieval.results[0]
    return SuggestResponse(
        answer=(
            f"Can tham chieu \"{top.title}\" v{top.version_number}, section {top.section}. "
            "Chi su dung noi dung published va escalate neu SOP khong noi ro policy."
        ),
        suggested_sops=[
            SuggestedSOP(
                sop_id=top.document_id,
                title=top.title,
                version=top.version_number,
                confidence=min(max(top.score, 0.0), 1.0),
            )
        ],
        citations=[top.citation],
        warnings=retrieval.warnings,
    )


@app.post("/ai/v1/summarize")
def summarize(payload: dict[str, Any]) -> SuggestResponse:
    query = str(payload.get("query") or payload.get("text") or "")
    retrieval = retrieve(RetrievalRequest(query=query, limit=5, mode="hybrid"))
    if not retrieval.results:
        return SuggestResponse(answer="Khong du nguon published de tom tat.", warnings=["missing_source"])
    steps = "; ".join(result.content[:220] for result in retrieval.results[:3])
    return SuggestResponse(answer=f"Cac diem lien quan: {steps}", citations=retrieval.citations)


@app.post("/ai/v1/evaluate-query")
def evaluate_query(payload: dict[str, str]) -> dict[str, Any]:
    query = payload.get("query", "")
    groups = repository.active_synonym_groups()
    normalized, expansions, matched_synonyms = expand_query(query, groups)
    return {
        "query": query,
        "normalized": normalized,
        "query_expansion": {
            "strategy": "db_managed_synonyms",
            "expansions": expansions,
            "matched_synonyms": matched_synonyms,
            "active_synonym_group_count": len(groups),
        },
        "looks_like_case_reason": normalized.startswith("cr "),
        "warnings": [] if normalized else ["empty_query"],
    }


def parse_metadata(value: str) -> DocumentMetadata:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_metadata_json") from exc
    return DocumentMetadata(**data)


def section_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(section_to_text(item) for item in value.values())
    return str(value)
