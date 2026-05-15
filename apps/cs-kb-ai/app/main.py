from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app import repository
from app.chat import grounded_chat, grounded_chat_session_message
from app.config import settings
from app.embedding import embed_text, embedding_runtime_metadata, remote_embedding_configured
from app.ingestion import prepare_document_version, preview_document_metadata
from app.retrieval import retrieve
from app.search_labels import embedding_text_for_unit, meaningful_search_label
from app.schemas import (
    BulkReviewVersionRequest,
    AssignRelationRequest,
    ChatSessionCreateRequest,
    ChatSessionMessageRequest,
    ChatSessionMessageResponse,
    ChatSessionSummary,
    ChatSessionUpdateRequest,
    ChatStoredMessage,
    CreateRelationRequest,
    DocumentMetadata,
    DocumentMetadataPreviewResponse,
    DocumentChunkSummary,
    DocumentRelation,
    DocumentSummary,
    DocumentVersionResponse,
    ExtractionJobSummary,
    ExtractionPipelineInspection,
    ExtractionUnit,
    ExtractionUnitCreateRequest,
    ExtractionUnitUpdateRequest,
    FeedbackQueueItem,
    GroundedChatRequest,
    GroundedChatResponse,
    ArchiveRelationRequest,
    ActionTemplateSummary,
    IssueRouterItem,
    IndexingResultRequest,
    IndexSOPVersionRequest,
    KBCollectionDetail,
    KBCollectionSummary,
    KBEventRequest,
    OpsAnalyticsResponse,
    PublishVersionRequest,
    RejectRelationRequest,
    RetrievalFilters,
    RetrievalRequest,
    RetrievalResponse,
    SearchFilterOptions,
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
    ToolLinkSummary,
    VersionRawTextResponse,
    VersionSummary,
)
from app.text_processing import chunk_text, classify_document, expand_query, extract_effective_date, extract_text


app = FastAPI(title="CS KB AI Service", version="0.2.0")
logger = logging.getLogger("cs_kb_ai")


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
    services.append(
        {
            "name": "embedding_provider",
            "status": "healthy" if remote_embedding_configured() else "skipped",
            "latency_ms": 0,
            "detail": f"{settings.embedding_provider}:{settings.embedding_model}:{settings.embedding_dimensions}",
        }
    )
    overall = "healthy" if all(service["status"] in {"healthy", "skipped"} for service in services) else "degraded"
    return {
        "status": overall,
        "service": "cs-kb-ai",
        "retrieval_store": "postgres_pgvector",
        "services": services,
    }


@app.get("/ai/v1/chat/model-routes")
def chat_model_routes() -> dict[str, Any]:
    return {
        "default_route": "simple",
        "routes": [
            {
                "route": "simple",
                "label": "Gemini Flash Lite",
                "model": settings.openrouter_chat_simple_model,
                "description": "Simple factual SOP Q&A.",
            },
            {
                "route": "policy",
                "label": "Kimi K2.5 Policy",
                "model": settings.openrouter_chat_policy_model,
                "description": "Policy, decision, and exception Q&A.",
            },
            {
                "route": "high_risk",
                "label": "Kimi K2.5 High Risk",
                "model": settings.openrouter_chat_high_risk_model,
                "description": "Refund, payment, account, privacy, ZT, and stricter citation-gated answers.",
            },
            {
                "route": "complex",
                "label": "Kimi K2.6 Complex",
                "model": settings.openrouter_chat_complex_model,
                "description": "Multi-SOP synthesis and polished macro drafting from published sources.",
            },
            {
                "route": "google/gemini-2.5-flash",
                "label": "Gemini 2.5 Flash",
                "model": settings.openrouter_chat_gemini_25_flash_model,
                "description": "Manual model override for balanced speed and quality on grounded SOP chat.",
            },
            {
                "route": "google/gemini-3-flash-preview",
                "label": "Gemini 3 Flash Preview",
                "model": settings.openrouter_chat_gemini_3_flash_model,
                "description": "Manual model override for newer Gemini reasoning on multi-source SOP questions.",
            },
            {
                "route": "anthropic/claude-3.5-haiku",
                "label": "Claude 3.5 Haiku",
                "model": settings.openrouter_chat_claude_35_haiku_model,
                "description": "Manual model override for concise grounded answers and quick policy checks.",
            },
        ],
        "fallback_model": settings.openrouter_chat_fallback_model,
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


PIPELINE_INSPECTION_STAGE_ORDER = [
    "map",
    "classify",
    "workflow_semantic_refine",
    "ai_structure",
    "plan",
    "reduce",
    "refine",
    "verify",
    "commit",
]


def build_extraction_pipeline_inspection(job: dict[str, Any]) -> dict[str, Any]:
    outputs = [dict(output) for output in job.get("outputs", []) if isinstance(output, dict)]
    stage_names = [
        *PIPELINE_INSPECTION_STAGE_ORDER,
        *[
            str(output.get("stage") or "")
            for output in outputs
            if output.get("stage") and str(output.get("stage")) not in PIPELINE_INSPECTION_STAGE_ORDER
        ],
    ]
    stage_summary = [
        stage_inspection_summary(stage, [output for output in outputs if output.get("stage") == stage])
        for stage in dict.fromkeys(stage_names)
    ]
    issue_summary = pipeline_issue_summary(outputs)
    inspection = {
        "version_id": str(job.get("version_id") or ""),
        "document_id": str(job.get("document_id") or ""),
        "job_id": str(job.get("id") or ""),
        "status": str(job.get("status") or "unknown"),
        "current_stage": str(job.get("current_stage") or ""),
        "source_type": str(job.get("source_type") or ""),
        "document_type": str(job.get("document_type") or "unknown"),
        "risk_level": str(job.get("risk_level") or ""),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "stage_order": list(dict.fromkeys(stage_names)),
        "stage_summary": stage_summary,
        "issue_summary": issue_summary,
        "artifacts": outputs,
    }
    inspection["summary_markdown"] = pipeline_inspection_markdown(inspection)
    return inspection


def stage_inspection_summary(stage: str, outputs: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    for output in outputs:
        warnings.extend(payload_warning_strings(output.get("payload")))
    return {
        "stage": stage,
        "output_count": len(outputs),
        "statuses": list(dict.fromkeys(str(output.get("status") or "completed") for output in outputs)),
        "artifact_types": list(dict.fromkeys(str(output.get("artifact_type") or "") for output in outputs if output.get("artifact_type"))),
        "errors": [str(output.get("error")) for output in outputs if output.get("error")],
        "warnings": warnings[:20],
        "summary": stage_summary_text(stage, outputs, warnings),
    }


def pipeline_issue_summary(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    hard_blockers: list[str] = []
    coverage_score: int | None = None
    warnings: list[str] = []
    for output in outputs:
        payload = output.get("payload") if isinstance(output.get("payload"), dict) else {}
        warnings.extend(payload_warning_strings(payload))
        if output.get("artifact_type") in {"verification_report", "publish_readiness_report"}:
            hard_blockers.extend(str(item) for item in payload.get("hard_blockers", []) if item)
            if payload.get("coverage_score") is not None:
                try:
                    coverage_score = int(payload.get("coverage_score"))
                except (TypeError, ValueError):
                    coverage_score = None
    return {
        "failed_output_count": sum(1 for output in outputs if output.get("status") == "failed"),
        "degraded_output_count": sum(1 for output in outputs if output.get("status") == "degraded"),
        "warning_count": len(list(dict.fromkeys(warnings))),
        "hard_blockers": list(dict.fromkeys(hard_blockers)),
        "coverage_score": coverage_score,
    }


def payload_warning_strings(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings if warning]


def stage_summary_text(stage: str, outputs: list[dict[str, Any]], warnings: list[str]) -> str:
    if not outputs:
        return "No artifact captured for this stage."
    failed = sum(1 for output in outputs if output.get("status") == "failed")
    degraded = sum(1 for output in outputs if output.get("status") == "degraded")
    artifacts = ", ".join(dict.fromkeys(str(output.get("artifact_type") or "artifact") for output in outputs))
    status = f"{failed} failed" if failed else f"{degraded} degraded" if degraded else "completed"
    warning_suffix = f", {len(warnings)} warning(s)" if warnings else ""
    return f"{stage}: {len(outputs)} artifact(s), {status}{warning_suffix}. {artifacts}"


def pipeline_inspection_markdown(inspection: dict[str, Any]) -> str:
    issue_summary = inspection.get("issue_summary") if isinstance(inspection.get("issue_summary"), dict) else {}
    lines = [
        f"# Extraction pipeline inspection",
        "",
        f"- Version: `{inspection.get('version_id', '')}`",
        f"- Document: `{inspection.get('document_id', '')}`",
        f"- Job: `{inspection.get('job_id', '')}`",
        f"- Status: `{inspection.get('status', 'unknown')}` at `{inspection.get('current_stage', '')}`",
        f"- Type: `{inspection.get('document_type', 'unknown')}` / `{inspection.get('source_type', '')}`",
        f"- Risk: `{inspection.get('risk_level', '')}`",
        "",
        "## Issues",
        "",
        f"- Failed outputs: {issue_summary.get('failed_output_count', 0)}",
        f"- Degraded outputs: {issue_summary.get('degraded_output_count', 0)}",
        f"- Warnings: {issue_summary.get('warning_count', 0)}",
        f"- Coverage score: {issue_summary.get('coverage_score') if issue_summary.get('coverage_score') is not None else 'n/a'}",
        f"- Hard blockers: {', '.join(issue_summary.get('hard_blockers') or []) or 'none'}",
        "",
        "## Stages",
        "",
    ]
    for stage in inspection.get("stage_summary", []):
        if not isinstance(stage, dict):
            continue
        lines.append(f"- `{stage.get('stage')}`: {stage.get('summary')}")
    lines.extend(["", "## Artifacts", ""])
    for artifact in inspection.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        label = f"{artifact.get('stage')} / {artifact.get('artifact_type')}"
        status = artifact.get("status") or "completed"
        error = str(artifact.get("error") or "")
        lines.append(f"- `{label}`: `{status}`{f' ({error})' if error else ''}")
    return "\n".join(lines).strip() + "\n"


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
        logger.warning(
            "document_upload_extraction_failed filename=%s content_type=%s reason=%s",
            file.filename,
            file.content_type,
            failure_reason,
        )
        raw_text, failure_chunks, failure_enrichment = failed_extraction_draft(
            filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            failure_reason=failure_reason,
            metadata=parsed_metadata,
        )
        failure_metadata = parsed_metadata.model_copy(
            update=failure_enrichment,
        )
        version = repository.create_document_version(
            external_id=external_id or digest,
            title=title or file.filename or digest,
            source_filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream",
            checksum=digest,
            raw_text=raw_text,
            raw_data=data,
            chunks=failure_chunks,
            metadata=failure_metadata,
            status="draft",
            created_by=created_by,
            change_summary=change_summary or f"Extraction failed: {failure_reason[:180]}",
            document_type=failure_enrichment["document_type"],
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
        logger.exception(
            "background_document_extraction_failed document_id=%s version_id=%s filename=%s reason=%s",
            document_id,
            version_id,
            filename,
            failure_reason,
        )
        raw_text, failure_chunks, failure_enrichment = failed_extraction_draft(
            filename=filename,
            content_type=content_type,
            data=data,
            failure_reason=failure_reason,
            metadata=metadata,
        )
        failed_metadata = metadata.model_copy(
            update=failure_enrichment,
        )
        repository.replace_document_version_extraction(
            document_id=document_id,
            version_id=version_id,
            raw_text=raw_text,
            chunks=failure_chunks,
            metadata=failed_metadata,
            document_type=failure_enrichment["document_type"],
            review_status="needs_review",
            extraction_confidence=0.0,
            actor=actor,
            change_summary=f"Background extraction failed: {failure_reason[:180]}",
        )


def failed_extraction_draft(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    failure_reason: str,
    metadata: DocumentMetadata,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    try:
        raw_text, extraction_warnings = extract_text(filename, content_type, data)
    except Exception as exc:
        raw_text = best_effort_raw_text(data)
        extraction_warnings = [f"raw_text_extraction_failed:{exc.__class__.__name__}"]
    classification = classify_document(filename, content_type, raw_text)
    effective_from = extract_effective_date(raw_text)
    source_ref_quality = "page_only" if filename.lower().endswith(".pdf") else "structured"
    base_metadata = {
        **metadata.model_dump(),
        "document_type": classification.document_type,
        "source_type": classification.source_type,
        "review_status": "needs_review",
        "extraction_confidence": 0.0,
        "extraction_status": "failed_validation",
        "extraction_error": failure_reason,
        "extraction_warnings": [failure_reason, *extraction_warnings, *classification.warnings],
        "source_filename": filename,
        "source_ref_quality": source_ref_quality,
        "source_ref_acknowledged": source_ref_quality != "page_only",
        "effective_from": effective_from,
        "publish_blocked_reason": "structured_ai_extraction_failed",
        "pipeline_current_stage": "verify",
        "pipeline_job_status": "failed",
        "pipeline_artifacts": [
            {
                "stage": "map",
                "artifact_type": "source_blocks",
                "status": "completed" if raw_text.strip() else "failed",
                "error": "" if raw_text.strip() else "raw_extraction_empty",
                "payload": {
                    "filename": filename,
                    "content_type": content_type,
                    "raw_text_chars": len(raw_text),
                    "source_ref_quality": source_ref_quality,
                    "warnings": extraction_warnings[:20],
                },
            },
            {
                "stage": "classify",
                "artifact_type": "classification_result",
                "status": "completed",
                "error": "",
                "payload": {
                    "document_type": classification.document_type,
                    "source_type": classification.source_type,
                    "confidence": classification.confidence,
                    "requires_review": True,
                    "signals": classification.warnings,
                },
            },
            {
                "stage": "ai_structure",
                "artifact_type": "ai_structured_payload",
                "status": "failed",
                "error": failure_reason,
                "payload": {"unit_count": 0, "warnings": [failure_reason]},
            },
            {
                "stage": "verify",
                "artifact_type": "verification_report",
                "status": "failed",
                "error": "",
                "payload": {
                    "coverage_score": 0,
                    "hard_blockers": ["extraction_failed", "manual_curation_required"],
                    "warnings": [failure_reason],
                },
            },
        ],
    }
    chunks: list[dict[str, Any]] = []
    embedding_metadata = embedding_runtime_metadata()
    if raw_text.strip():
        chunks.append(
            {
                "chunk_index": 0,
                "section": "full_sop",
                "heading": filename.rsplit(".", 1)[0][:180] or "Raw source evidence",
                "content": raw_text,
                "token_count": len(raw_text.split()),
                "embedding": embed_text(raw_text[:4000]),
                "metadata": {
                    **base_metadata,
                    **embedding_metadata,
                    "unit_type": "full_sop",
                    "retrieval_scope": "document",
                    "source_evidence_only": True,
                },
            }
        )
        for source_chunk in chunk_text(raw_text)[:12]:
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "section": source_chunk.section or "text_section",
                    "heading": source_chunk.heading or "Raw extracted section",
                    "content": source_chunk.content,
                    "token_count": source_chunk.token_count,
                    "embedding": embed_text(" ".join([source_chunk.heading, source_chunk.content])),
                    "metadata": {
                        **base_metadata,
                        **source_chunk.metadata,
                        **embedding_metadata,
                        "unit_type": "text_section",
                        "retrieval_scope": "unit",
                        "source_evidence_only": True,
                    },
                }
            )
    return raw_text, chunks, base_metadata


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


@app.get("/ai/v1/relations", response_model=list[DocumentRelation])
def list_relations(status: str = "unresolved") -> list[DocumentRelation]:
    return [DocumentRelation(**row) for row in repository.list_document_relations(status)]


@app.post("/ai/v1/relations", response_model=DocumentRelation)
def create_relation(payload: CreateRelationRequest) -> DocumentRelation:
    try:
        return DocumentRelation(
            **repository.create_document_relation(
                source_document_id=payload.source_document_id,
                source_version_id=payload.source_version_id,
                source_chunk_id=payload.source_chunk_id,
                target_title=payload.target_title,
                target_document_id=payload.target_document_id,
                relation_type=payload.relation_type,
                actor=payload.actor,
                metadata=payload.metadata,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/relations/{relation_id}/assign", response_model=DocumentRelation)
def assign_relation(relation_id: str, payload: AssignRelationRequest) -> DocumentRelation:
    try:
        return DocumentRelation(**repository.assign_document_relation(relation_id, payload.target_document_id, payload.actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/relations/{relation_id}/reject", response_model=DocumentRelation)
def reject_relation(relation_id: str, payload: RejectRelationRequest | None = None) -> DocumentRelation:
    data = payload or RejectRelationRequest()
    try:
        return DocumentRelation(**repository.reject_document_relation(relation_id, data.actor, data.rejection_reason))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/ai/v1/relations/{relation_id}/archive", response_model=DocumentRelation)
def archive_relation(relation_id: str, payload: ArchiveRelationRequest | None = None) -> DocumentRelation:
    data = payload or ArchiveRelationRequest()
    try:
        return DocumentRelation(**repository.archive_document_relation(relation_id, data.actor, data.archive_reason))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ai/v1/collections", response_model=list[KBCollectionSummary])
def list_collections() -> list[KBCollectionSummary]:
    return [KBCollectionSummary(**row) for row in repository.list_kb_collections()]


@app.get("/ai/v1/search/filter-options", response_model=SearchFilterOptions)
def list_search_filter_options() -> SearchFilterOptions:
    return SearchFilterOptions(**repository.list_search_filter_options())


@app.get("/ai/v1/collections/{collection_id}", response_model=KBCollectionDetail)
def get_collection(collection_id: str) -> KBCollectionDetail:
    try:
        return KBCollectionDetail(**repository.get_kb_collection(collection_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ai/v1/issue-router", response_model=list[IssueRouterItem])
def list_issue_router(
    query: str = "",
    audience: str = "",
    vertical: str = "",
    collection: str = "",
    task_type: str = "",
    risk_level: str = "",
    limit: int = 50,
) -> list[IssueRouterItem]:
    return [
        IssueRouterItem(**row)
        for row in repository.list_issue_router(
            query=query,
            audience=split_query_values(audience),
            vertical=split_query_values(vertical),
            collection=collection,
            task_type=split_query_values(task_type),
            risk_level=risk_level,
            limit=min(max(limit, 1), 100),
        )
    ]


@app.get("/ai/v1/tools", response_model=list[ToolLinkSummary])
def list_tools(status: str = "active", collection: str = "") -> list[ToolLinkSummary]:
    return [ToolLinkSummary(**row) for row in repository.list_tool_links(status=status, collection=collection)]


@app.get("/ai/v1/action-templates", response_model=list[ActionTemplateSummary])
def list_action_templates(status: str = "approved", collection: str = "") -> list[ActionTemplateSummary]:
    return [ActionTemplateSummary(**row) for row in repository.list_action_templates(status=status, collection=collection)]


@app.post("/ai/v1/kb-events")
def record_kb_event(payload: KBEventRequest) -> dict[str, str]:
    return repository.record_kb_event(payload.action, payload.entity_type, payload.entity_id, payload.actor, payload.metadata)


@app.get("/ai/v1/feedback/queue", response_model=list[FeedbackQueueItem])
def list_feedback_queue(limit: int = 500) -> list[FeedbackQueueItem]:
    return [FeedbackQueueItem(**row) for row in repository.list_feedback_queue(limit=limit)]


@app.get("/ai/v1/analytics/ops", response_model=OpsAnalyticsResponse)
def ops_analytics(window_days: int = 7) -> OpsAnalyticsResponse:
    return OpsAnalyticsResponse(**repository.ops_analytics(window_days=window_days))


def split_query_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.get("/ai/v1/documents/{document_id}/versions", response_model=list[VersionSummary])
def list_document_versions(document_id: str) -> list[VersionSummary]:
    return [VersionSummary(**row) for row in repository.list_versions(document_id)]


@app.get("/ai/v1/documents/{document_id}/chunks", response_model=list[DocumentChunkSummary])
def list_document_chunks(document_id: str, version_id: str = "") -> list[DocumentChunkSummary]:
    return [DocumentChunkSummary(**row) for row in repository.list_chunks(document_id, version_id)]


@app.get("/ai/v1/documents/{document_id}/extraction-units", response_model=list[ExtractionUnit])
def list_document_extraction_units(document_id: str, version_id: str = "") -> list[ExtractionUnit]:
    return [ExtractionUnit(**row) for row in repository.list_extraction_units(document_id, version_id)]


@app.get("/ai/v1/versions/{version_id}/extraction-pipeline", response_model=list[ExtractionJobSummary])
def list_version_extraction_pipeline(version_id: str) -> list[ExtractionJobSummary]:
    return [ExtractionJobSummary(**row) for row in repository.list_extraction_pipeline(version_id)]


@app.get("/ai/v1/versions/{version_id}/extraction-pipeline/inspection", response_model=ExtractionPipelineInspection)
def inspect_version_extraction_pipeline(version_id: str) -> ExtractionPipelineInspection:
    jobs = repository.list_extraction_pipeline(version_id)
    if not jobs:
        raise HTTPException(status_code=404, detail="extraction_pipeline_not_found")
    return ExtractionPipelineInspection(**build_extraction_pipeline_inspection(jobs[0]))


@app.get("/ai/v1/versions/{version_id}/extraction-pipeline/inspection.md")
def inspect_version_extraction_pipeline_markdown(version_id: str) -> Response:
    jobs = repository.list_extraction_pipeline(version_id)
    if not jobs:
        raise HTTPException(status_code=404, detail="extraction_pipeline_not_found")
    inspection = build_extraction_pipeline_inspection(jobs[0])
    return Response(content=inspection["summary_markdown"], media_type="text/plain; charset=utf-8")


@app.patch("/ai/v1/extraction-units/{unit_id}", response_model=ExtractionUnit)
def update_extraction_unit(unit_id: str, request: ExtractionUnitUpdateRequest) -> ExtractionUnit:
    try:
        unit = repository.update_extraction_unit(
            unit_id=unit_id,
            title=meaningful_search_label(request.title, request.content, request.unit_type),
            content=request.content,
            unit_type=request.unit_type,
            confidence=request.confidence,
            review_status=request.review_status,
            metadata={**request.metadata, **embedding_runtime_metadata()},
            actor=request.actor,
            embedding=embed_text(embedding_text_for_unit(request.title, request.content, request.unit_type)),
        )
        return ExtractionUnit(**unit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/versions/{version_id}/extraction-units", response_model=ExtractionUnit)
def create_extraction_unit(version_id: str, request: ExtractionUnitCreateRequest) -> ExtractionUnit:
    try:
        unit = repository.create_extraction_unit(
            version_id=version_id,
            title=meaningful_search_label(request.title, request.content, request.unit_type),
            content=request.content,
            unit_type=request.unit_type,
            confidence=request.confidence,
            review_status=request.review_status,
            metadata={**request.metadata, **embedding_runtime_metadata()},
            actor=request.actor,
            embedding=embed_text(embedding_text_for_unit(request.title, request.content, request.unit_type)),
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
def publish_version(version_id: str, payload: PublishVersionRequest | None = None) -> dict[str, Any]:
    try:
        data = payload or PublishVersionRequest()
        return repository.publish_version(version_id, data.actor, data.force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/versions/{version_id}/retry-indexing")
def retry_version_indexing(version_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        actor = str((payload or {}).get("actor") or "api-gateway")
        return repository.prepare_version_indexing_retry(version_id, actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/versions/{version_id}/indexing-result")
def mark_version_indexing_result(version_id: str, payload: IndexingResultRequest) -> dict[str, Any]:
    try:
        return repository.mark_version_indexing_result(
            version_id,
            actor=payload.actor,
            success=payload.success,
            lexical_index_synced=payload.lexical_index_synced,
            vector_index_verified=payload.vector_index_verified,
            error=payload.error,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/ai/v1/versions/{version_id}/publish-readiness")
def get_publish_readiness(version_id: str) -> dict[str, Any]:
    try:
        return repository.publish_readiness(version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/ai/v1/versions/{version_id}/bulk-review")
def bulk_review_version(version_id: str, payload: BulkReviewVersionRequest | None = None) -> dict[str, Any]:
    try:
        data = payload or BulkReviewVersionRequest()
        return repository.bulk_review_version(
            version_id,
            data.actor,
            data.review_status,
            data.scope,
            data.force,
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


@app.get("/ai/v1/chat/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(status: str = "active") -> list[ChatSessionSummary]:
    return [ChatSessionSummary(**row) for row in repository.list_chat_sessions(status)]


@app.post("/ai/v1/chat/sessions", response_model=ChatSessionSummary)
def create_chat_session(payload: ChatSessionCreateRequest) -> ChatSessionSummary:
    return ChatSessionSummary(**repository.create_chat_session(payload.title, payload.model_route, payload.filters))


@app.post("/ai/v1/chat/sessions/{session_id}/update", response_model=ChatSessionSummary)
def update_chat_session(session_id: str, payload: ChatSessionUpdateRequest) -> ChatSessionSummary:
    try:
        return ChatSessionSummary(
            **repository.update_chat_session(
                session_id,
                title=payload.title,
                status=payload.status,
                model_route=payload.model_route,
                filters=payload.filters,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ai/v1/chat/sessions/{session_id}/messages", response_model=list[ChatStoredMessage])
def list_chat_session_messages(session_id: str) -> list[ChatStoredMessage]:
    try:
        return [ChatStoredMessage(**row) for row in repository.list_chat_messages(session_id)]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/ai/v1/chat/sessions/{session_id}/messages", response_model=ChatSessionMessageResponse)
def create_chat_session_message(session_id: str, payload: ChatSessionMessageRequest) -> ChatSessionMessageResponse:
    try:
        return ChatSessionMessageResponse(**grounded_chat_session_message(session_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
