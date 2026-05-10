from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app import repository
from app.chat import grounded_chat
from app.config import settings
from app.embedding import embed_text
from app.ingestion import prepare_document_version, preview_document_metadata
from app.retrieval import retrieve
from app.schemas import (
    DocumentMetadata,
    DocumentMetadataPreviewResponse,
    DocumentChunkSummary,
    DocumentSummary,
    DocumentVersionResponse,
    ExtractionUnit,
    ExtractionUnitUpdateRequest,
    GroundedChatRequest,
    GroundedChatResponse,
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
    VersionRawTextResponse,
    VersionSummary,
)
from app.text_processing import expand_query


app = FastAPI(title="CS KB AI Service", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    repository.ensure_schema()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    services: list[dict[str, Any]] = [
        {
            "name": "ai_service",
            "status": "healthy",
            "latency_ms": 0,
            "detail": "FastAPI process is serving requests",
        }
    ]
    try:
        db_status = repository.health_check()
        services.append({"name": "ai_postgres_pgvector", **db_status})
    except Exception as exc:
        services.append(
            {
                "name": "ai_postgres_pgvector",
                "status": "down",
                "latency_ms": 0,
                "detail": exc.__class__.__name__,
            }
        )

    services.append(qdrant_health())
    overall = "healthy" if all(service["status"] in {"healthy", "skipped"} for service in services) else "degraded"
    return {
        "status": overall,
        "service": "cs-kb-ai",
        "retrieval_store": "postgres_pgvector",
        "services": services,
    }


def qdrant_health() -> dict[str, Any]:
    if not settings.qdrant_url:
        return {
            "name": "qdrant",
            "status": "skipped",
            "latency_ms": 0,
            "detail": "QDRANT_URL is not configured; retrieval is using Postgres pgvector",
        }
    target = settings.qdrant_url.rstrip("/") + "/readyz"
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else None
    start = time.perf_counter()
    try:
        response = httpx.get(target, headers=headers, timeout=3)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code < 300:
            return {
                "name": "qdrant",
                "status": "healthy",
                "latency_ms": latency_ms,
                "detail": "Qdrant ready endpoint is reachable",
            }
        return {
            "name": "qdrant",
            "status": "degraded",
            "latency_ms": latency_ms,
            "detail": f"HTTP {response.status_code}",
        }
    except Exception as exc:
        return {
            "name": "qdrant",
            "status": "down",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "detail": exc.__class__.__name__,
        }


@app.post("/ai/v1/documents/upload", response_model=DocumentVersionResponse)
async def upload_document(
    file: UploadFile = File(...),
    external_id: str = Form(""),
    title: str = Form(""),
    status: str = Form("draft"),
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

    try:
        raw_text, digest, chunks, warnings, enrichment = prepare_document_version(
            filename=file.filename or "document.txt",
            content_type=file.content_type or "text/plain",
            data=data,
            metadata=parsed_metadata,
        )
    except ValueError as exc:
        digest = hashlib.sha256(data).hexdigest()
        failure_reason = str(exc)
        failure_metadata = parsed_metadata.model_copy(
            update={
                "review_status": "needs_review",
                "extraction_confidence": 0.0,
                "extraction_status": "failed_validation",
                "extraction_error": failure_reason,
                "extraction_warnings": [failure_reason],
            }
        )
        version = repository.create_document_version(
            external_id=external_id or digest,
            title=title or file.filename or digest,
            source_filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream",
            checksum=digest,
            raw_text=best_effort_raw_text(data),
            raw_data=data,
            chunks=[],
            metadata=failure_metadata,
            status="draft",
            created_by=created_by,
            change_summary=change_summary or f"Extraction failed: {failure_reason[:180]}",
            document_type=failure_metadata.document_type,
            review_status="needs_review",
            extraction_confidence=0.0,
        )
        return DocumentVersionResponse(**version, warnings=[failure_reason])
    if not chunks:
        warnings = [*warnings, "no_chunks_created"]

    parsed_metadata = parsed_metadata.model_copy(update=enrichment)
    version = repository.create_document_version(
        external_id=external_id or digest,
        title=title or file.filename or digest,
        source_filename=file.filename or "document.txt",
        content_type=file.content_type or "text/plain",
        checksum=digest,
        raw_text=raw_text,
        raw_data=data,
        chunks=chunks,
        metadata=parsed_metadata,
        status=status,
        created_by=created_by,
        change_summary=change_summary,
        document_type=enrichment["document_type"],
        review_status="approved" if status == "published" else enrichment["review_status"],
        extraction_confidence=enrichment["extraction_confidence"],
    )
    return DocumentVersionResponse(**version, warnings=warnings)


@app.post("/ai/v1/documents/upload-async", response_model=DocumentVersionResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    external_id: str = Form(""),
    title: str = Form(""),
    metadata: str = Form("{}"),
    created_by: str = Form("system"),
    change_summary: str = Form("Uploaded for background extraction"),
) -> DocumentVersionResponse:
    parsed_metadata = parse_metadata(metadata)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")

    digest = hashlib.sha256(data).hexdigest()
    pending_metadata = parsed_metadata.model_copy(
        update={
            "review_status": "needs_review",
            "extraction_confidence": 0.0,
            "extraction_status": "extracting",
            "extraction_error": "",
            "extraction_warnings": ["background_extraction_queued"],
        }
    )
    version = repository.create_document_version(
        external_id=external_id or digest,
        title=title or file.filename or digest,
        source_filename=file.filename or "document.txt",
        content_type=file.content_type or "application/octet-stream",
        checksum=digest,
        raw_text=best_effort_raw_text(data),
        raw_data=data,
        chunks=[],
        metadata=pending_metadata,
        status="draft",
        created_by=created_by,
        change_summary=change_summary,
        document_type=pending_metadata.document_type,
        review_status="needs_review",
        extraction_confidence=0.0,
    )
    background_tasks.add_task(
        run_background_extraction,
        document_id=version["document_id"],
        version_id=version["version_id"],
        filename=file.filename or "document.txt",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        metadata=parsed_metadata,
        actor=created_by,
    )
    return DocumentVersionResponse(**version, warnings=["background_extraction_queued"])


def run_background_extraction(
    *,
    document_id: str,
    version_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    metadata: DocumentMetadata,
    actor: str,
) -> None:
    try:
        raw_text, _digest, chunks, warnings, enrichment = prepare_document_version(
            filename=filename,
            content_type=content_type,
            data=data,
            metadata=metadata,
        )
        extracted_metadata = metadata.model_copy(update=enrichment)
        repository.replace_document_version_extraction(
            document_id=document_id,
            version_id=version_id,
            raw_text=raw_text,
            chunks=chunks,
            metadata=extracted_metadata,
            document_type=enrichment["document_type"],
            review_status=enrichment["review_status"],
            extraction_confidence=enrichment["extraction_confidence"],
            actor=actor,
            change_summary="Background extraction completed",
        )
    except Exception as exc:
        failure_reason = str(exc)
        failed_metadata = metadata.model_copy(
            update={
                "review_status": "needs_review",
                "extraction_confidence": 0.0,
                "extraction_status": "failed_validation",
                "extraction_error": failure_reason,
                "extraction_warnings": [failure_reason],
            }
        )
        repository.replace_document_version_extraction(
            document_id=document_id,
            version_id=version_id,
            raw_text=best_effort_raw_text(data),
            chunks=[],
            metadata=failed_metadata,
            document_type=failed_metadata.document_type,
            review_status="needs_review",
            extraction_confidence=0.0,
            actor=actor,
            change_summary=f"Background extraction failed: {failure_reason[:180]}",
        )


@app.post("/ai/v1/documents/metadata-preview", response_model=DocumentMetadataPreviewResponse)
async def preview_document_upload_metadata(file: UploadFile = File(...)) -> DocumentMetadataPreviewResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")
    try:
        preview = preview_document_metadata(
            filename=file.filename or "document.txt",
            content_type=file.content_type or "text/plain",
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentMetadataPreviewResponse(**preview)


@app.get("/ai/v1/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return [DocumentSummary(**row) for row in repository.list_documents()]


@app.get("/ai/v1/documents/{document_id}/versions", response_model=list[VersionSummary])
def list_document_versions(document_id: str) -> list[VersionSummary]:
    return [VersionSummary(**row) for row in repository.list_versions(document_id)]


@app.get("/ai/v1/documents/{document_id}/chunks", response_model=list[DocumentChunkSummary])
def list_document_chunks(document_id: str, version_id: str = "") -> list[DocumentChunkSummary]:
    return [DocumentChunkSummary(**row) for row in repository.list_chunks(document_id, version_id)]


@app.get("/ai/v1/documents/{document_id}/extraction-units", response_model=list[ExtractionUnit])
def list_document_extraction_units(document_id: str, version_id: str = "") -> list[ExtractionUnit]:
    return [ExtractionUnit(**row) for row in repository.list_extraction_units(document_id, version_id)]


@app.patch("/ai/v1/extraction-units/{unit_id}", response_model=ExtractionUnit)
def update_extraction_unit(unit_id: str, request: ExtractionUnitUpdateRequest) -> ExtractionUnit:
    try:
        unit = repository.update_extraction_unit(
            unit_id=unit_id,
            title=request.title,
            content=request.content,
            unit_type=request.unit_type,
            confidence=request.confidence,
            review_status=request.review_status,
            metadata=request.metadata,
            actor=request.actor,
            embedding=embed_text(" ".join([request.title, request.content])),
        )
        return ExtractionUnit(**unit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/ai/v1/versions/{version_id}/raw", response_model=VersionRawTextResponse)
def get_version_raw_text(version_id: str) -> VersionRawTextResponse:
    try:
        return VersionRawTextResponse(**repository.version_raw_text(version_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ai/v1/versions/{version_id}/source/pages/{page_number}")
def get_version_source_page(version_id: str, page_number: int) -> Response:
    try:
        image = repository.version_source_page_image(version_id, page_number)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@app.post("/ai/v1/versions/{version_id}/publish")
def publish_version(version_id: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        return repository.publish_version(version_id, (payload or {}).get("actor", "system"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/versions/{version_id}/bulk-review")
def bulk_review_version(version_id: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        return repository.bulk_review_version(
            version_id,
            (payload or {}).get("actor", "system"),
            (payload or {}).get("review_status", "reviewed"),
            (payload or {}).get("scope", "all"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@app.post("/ai/v1/chat", response_model=GroundedChatResponse)
def chat(request: GroundedChatRequest) -> GroundedChatResponse:
    return grounded_chat(request)


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
    _, digest, chunks, warnings, enrichment = prepare_document_version(
        filename=f"{request.sop_id}-{request.version_id}.txt",
        content_type="text/plain",
        data=data,
        metadata=metadata,
    )
    metadata = metadata.model_copy(update=enrichment)
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
        document_type=enrichment["document_type"],
        review_status="approved",
        extraction_confidence=enrichment["extraction_confidence"],
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


def best_effort_raw_text(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="replace").replace("\x00", "")[:200000]
    except Exception:
        return ""


def section_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(section_to_text(item) for item in value.values())
    return str(value)
