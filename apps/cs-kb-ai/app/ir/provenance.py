from __future__ import annotations

import hashlib
import re
from typing import Any

from app.ir.schema import Provenance, excerpt_hash


IR_PARSER_VERSION = "document_evidence_graph_v1"


def artifact_id_for(filename: str, data: bytes) -> str:
    digest = hashlib.sha256(data or b"").hexdigest()[:16]
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", filename.rsplit("/", 1)[-1]).strip("_").lower()[:60]
    return f"artifact_{slug or 'upload'}_{digest}"


def source_locator_for_ref(ref: dict[str, Any]) -> dict[str, Any]:
    locator = {key: value for key, value in ref.items() if value not in (None, "", [])}
    if "source_type" not in locator and ref.get("type"):
        locator["source_type"] = ref["type"]
    return locator


def source_locator_for_block(filename: str, content_type: str, block: dict[str, Any]) -> dict[str, Any]:
    source_type = "text"
    lower = filename.lower()
    if lower.endswith(".pdf") or content_type == "application/pdf":
        source_type = "pdf"
    elif lower.endswith(".docx"):
        source_type = "docx"
    elif lower.endswith((".xlsx", ".xlsm", ".xls")):
        source_type = "excel"
    locator: dict[str, Any] = {"source_type": source_type, "source_file": filename}
    if block.get("source_refs") and isinstance(block["source_refs"], list) and isinstance(block["source_refs"][0], dict):
        locator.update(source_locator_for_ref(block["source_refs"][0]))
    for key in (
        "page",
        "paragraph_index",
        "table_index",
        "row_index",
        "line_start",
        "line_end",
        "sheet",
        "sheet_name",
        "bbox",
        "cell_ref",
        "column_names",
    ):
        if block.get(key) not in (None, "", []):
            locator[key] = block[key]
    if "line_start" not in locator and block.get("index") is not None and source_type == "text":
        locator["line_start"] = int(block.get("index") or 0) + 1
        locator["line_end"] = int(block.get("index") or 0) + 1
    return locator


def provenance_for_block(
    filename: str,
    content_type: str,
    block: dict[str, Any],
    parser_name: str = "local_parser",
    extraction_method: str = "deterministic",
) -> Provenance:
    return Provenance(
        parser_name=parser_name,
        parser_version=IR_PARSER_VERSION,
        extraction_method=extraction_method,
        source_locator=source_locator_for_block(filename, content_type, block),
        raw_excerpt_hash=excerpt_hash(str(block.get("text") or block.get("content") or "")),
    )
