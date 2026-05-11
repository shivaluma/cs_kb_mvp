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
from app.chat import grounded_chat
from app.config import settings
from app.embedding import embed_text
from app.ingestion import prepare_document_version, preview_document_metadata
from app.retrieval import retrieve
from app.schemas import (
    BulkReviewVersionRequest,
    DocumentMetadata,
    DocumentMetadataPreviewResponse,
    DocumentChunkSummary,
    DocumentSummary,
    DocumentVersionResponse,
    ExtractionJobSummary,
    ExtractionPipelineInspection,
    ExtractionUnit,
    ExtractionUnitCreateRequest,
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


@app.post("/ai/v1/versions/{version_id}/extraction-units", response_model=ExtractionUnit)
def create_extraction_unit(version_id: str, request: ExtractionUnitCreateRequest) -> ExtractionUnit:
    try:
        unit = repository.create_extraction_unit(
            version_id=version_id,
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
