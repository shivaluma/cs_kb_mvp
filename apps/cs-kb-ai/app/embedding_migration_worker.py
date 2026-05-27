from __future__ import annotations

from typing import Any

from app import repository


DEFAULT_MIGRATION_STATUSES = ("pending", "in_progress")


def run_pending_embedding_migrations(
    *,
    batch_size: int = 100,
    max_batches: int = 10,
    statuses: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    safe_batch_size = max(1, min(int(batch_size or 100), 1000))
    safe_max_batches = max(0, int(max_batches or 0))
    status_filter = _clean_statuses(statuses or DEFAULT_MIGRATION_STATUSES)
    summary: dict[str, Any] = {
        "batch_count": 0,
        "batch_size": safe_batch_size,
        "job_count": 0,
        "jobs": [],
        "max_batches": safe_max_batches,
        "processed_items": 0,
        "remaining_items": 0,
        "statuses": status_filter,
        "stopped_reason": "max_batches" if safe_max_batches == 0 else "",
    }
    job_summaries: dict[str, dict[str, Any]] = {}

    for _batch_index in range(safe_max_batches):
        jobs = repository.list_embedding_migration_jobs(statuses=status_filter, limit=1)
        if not jobs:
            summary["stopped_reason"] = "no_jobs"
            break

        job_id = str(jobs[0].get("id") or "")
        if not job_id:
            summary["stopped_reason"] = "missing_job_id"
            break

        result = repository.run_embedding_migration_job(job_id, batch_size=safe_batch_size)
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        processed_batch = _int_value(metadata.get("processed_batch"))
        remaining_items = _int_value(metadata.get("remaining_items"))

        summary["batch_count"] = int(summary["batch_count"]) + 1
        summary["processed_items"] = int(summary["processed_items"]) + processed_batch
        summary["remaining_items"] = remaining_items

        job_summaries[job_id] = {
            "id": job_id,
            "processed_items": _int_value(result.get("processed_items")),
            "remaining_items": remaining_items,
            "status": str(result.get("status") or ""),
            "total_items": _int_value(result.get("total_items")),
        }

        if result.get("status") == "failed":
            summary["stopped_reason"] = "failed"
            break
        if processed_batch <= 0 and result.get("status") != "completed":
            summary["stopped_reason"] = "no_progress"
            break

    if not summary["stopped_reason"]:
        summary["stopped_reason"] = "max_batches"
    summary["jobs"] = list(job_summaries.values())
    summary["job_count"] = len(job_summaries)
    return summary


def _clean_statuses(statuses: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(str(status or "").strip() for status in statuses if str(status or "").strip()))


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
