from __future__ import annotations

import hashlib
import io
import base64
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from docx import Document as DocxDocument
from openpyxl import load_workbook
from pypdf import PdfReader

from app.config import settings


WORD_RE = re.compile(r"[\w]+", re.UNICODE)
HEADING_RE = re.compile(r"^\s*(#{1,6}\s+|[A-Z][A-Z0-9 _/-]{5,}:)\s*(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    section: str
    heading: str
    content: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    source_type: str
    confidence: float
    requires_review: bool
    warnings: list[str] = field(default_factory=list)


def classify_document(filename: str, content_type: str, raw_text: str = "") -> DocumentClassification:
    lower_name = filename.lower()
    normalized = normalize_phrase(raw_text[:5000])

    if is_spreadsheet_file(lower_name, content_type):
        return DocumentClassification("policy_table", "spreadsheet", 0.92, True)
    if is_image_file(lower_name, content_type):
        return DocumentClassification(
            "asset_sop",
            "image",
            0.72,
            True,
            ["image_ocr_or_vision_extraction_required"],
        )
    if lower_name.endswith(".pdf") and looks_like_workflow(normalized):
        return DocumentClassification("workflow_diagram", "diagram_pdf", 0.78, True)
    if looks_like_email_policy(lower_name, normalized):
        return DocumentClassification(
            "policy_rule",
            "docx_policy_rule" if lower_name.endswith(".docx") else "text_policy_rule",
            0.9,
            True,
            ["effective_from_missing_needs_review"],
        )
    if any(term in normalized for term in ["macro", "script", "cau tra loi", "phan hoi mau"]):
        return DocumentClassification("macro_script", "text", 0.72, True)
    if lower_name.endswith((".pdf", ".docx", ".md", ".txt")):
        return DocumentClassification("text_sop", "text", 0.84, True)
    return DocumentClassification("unknown", "upload", 0.35, True, ["unknown_document_type"])


def extract_text(filename: str, content_type: str, data: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lower_name = filename.lower()

    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"file_too_large:{settings.max_upload_bytes}")

    if is_image_file(lower_name, content_type):
        text = (
            f"Image asset uploaded: {filename}. OCR/vision extraction is not configured in this local MVP. "
            "Keep this version in draft and curate the SOP manually before publishing."
        )
        warnings.append("image_ocr_or_vision_extraction_required")
    elif lower_name.endswith(".pdf") or content_type == "application/pdf":
        text = extract_pdf_text(data)
    elif is_spreadsheet_file(lower_name, content_type):
        text, spreadsheet_warnings, _ = extract_spreadsheet(lower_name, data)
        warnings.extend(spreadsheet_warnings)
    elif lower_name.endswith(".docx") or content_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        text = extract_docx_text(data)
    else:
        text = data.decode("utf-8", errors="ignore")

    text = normalize_whitespace(text)
    if not text:
        warnings.append("empty_text_after_extraction")
    return text, warnings


def is_spreadsheet_file(filename: str, content_type: str) -> bool:
    return filename.endswith((".xlsx", ".xlsm", ".xls")) or content_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/vnd.ms-excel",
    }


def is_image_file(filename: str, content_type: str) -> bool:
    return filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff")) or content_type.startswith("image/")


def looks_like_workflow(normalized_text: str) -> bool:
    workflow_terms = [
        "yes",
        "no",
        "co",
        "khong",
        "decision",
        "flow",
        "quy trinh",
        "xac minh",
        "neu",
        "truong hop",
    ]
    hits = sum(1 for term in workflow_terms if phrase_in_query(term, normalized_text))
    return hits >= 4


def looks_like_email_policy(lower_name: str, normalized_text: str) -> bool:
    source = normalize_phrase(lower_name) + " " + normalized_text
    signals = [
        "email" in source or "mail" in source,
        "xac minh" in source or "quy dinh" in source,
        "zt" in source or "bizops" in source or "admin" in source,
        "sai dinh dang" in source or "khong nhan duoc" in source,
    ]
    return sum(1 for hit in signals if hit) >= 3


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for index, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"\n\n[page {index + 1}]\n{page_text}")
    return "\n".join(pages)


def render_pdf_pages_as_data_urls(data: bytes, max_pages: int = 3, scale: float = 1.6) -> tuple[list[str], list[str]]:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return [], ["pdf_vision_render_unavailable:pypdfium2_missing"]

    try:
        pdf = pdfium.PdfDocument(data)
        images: list[str] = []
        for page_index in range(min(len(pdf), max_pages)):
            page = pdf[page_index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=82, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            images.append(f"data:image/jpeg;base64,{encoded}")
        if not images:
            return [], ["pdf_vision_render_empty"]
        return images, [f"pdf_vision_pages_rendered:{len(images)}"]
    except Exception as exc:
        return [], [f"pdf_vision_render_failed:{exc.__class__.__name__}"]


def render_pdf_page_jpeg(data: bytes, page_number: int = 1, scale: float = 1.8) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    if page_number < 1 or page_number > len(pdf):
        raise IndexError("page_out_of_range")
    page = pdf[page_number - 1]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    return buffer.getvalue()


def extract_docx_text(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    blocks = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))
    return "\n".join(blocks)


def extract_spreadsheet(filename: str, data: bytes) -> tuple[str, list[str], list[Chunk]]:
    warnings: list[str] = []
    raw_blocks: list[str] = []
    chunks: list[Chunk] = []
    sheets = spreadsheet_rows(filename, data)

    for sheet_name, rows in sheets:
        section = slugify(sheet_name)[:80] or "sheet"
        sheet_chunks = spreadsheet_sheet_chunks(rows, section, sheet_name, len(chunks))
        if not sheet_chunks:
            warnings.append(f"sheet_empty:{sheet_name}")
            continue
        raw_blocks.append(f"# {sheet_name}")
        for chunk in sheet_chunks:
            raw_blocks.append(f"## {chunk.heading}\n{chunk.content}")
            chunks.append(chunk)

    raw_text = "\n\n".join(raw_blocks)
    if not chunks:
        warnings.append("spreadsheet_no_indexable_rows")
    return raw_text, warnings, reindex_chunks(chunks)


def spreadsheet_rows(filename: str, data: bytes) -> list[tuple[str, list[tuple[int, list[str]]]]]:
    if filename.endswith(".xls") and not filename.endswith((".xlsx", ".xlsm")):
        import xlrd

        workbook = xlrd.open_workbook(file_contents=data)
        sheets = []
        for sheet in workbook.sheets():
            rows = []
            for row_index in range(sheet.nrows):
                values = [cell_to_text(sheet.cell_value(row_index, col_index)) for col_index in range(sheet.ncols)]
                if any(values):
                    rows.append((row_index + 1, trim_trailing_empty(values)))
            sheets.append((sheet.name.strip(), rows))
        return sheets

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = []
    for worksheet in workbook.worksheets:
        rows = []
        for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
            values = [cell_to_text(value) for value in row]
            if any(values):
                rows.append((row_number, trim_trailing_empty(values)))
        sheets.append((worksheet.title.strip(), rows))
    return sheets


def spreadsheet_sheet_chunks(non_empty_rows: list[tuple[int, list[str]]], section: str, sheet_name: str, start_index: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    context: list[str] = []
    header_candidates: list[tuple[int, list[str]]] = []
    seen_data = False

    for row_number, values in non_empty_rows:
        filled_count = sum(1 for value in values if value)
        if filled_count == 0:
            continue

        if filled_count == 1:
            text = next(value for value in values if value)
            if not seen_data and len(text) <= 140:
                context.append(text)
                continue
            chunks.append(spreadsheet_chunk(start_index + len(chunks), section, sheet_name, row_number, context, "", text, values))
            seen_data = True
            continue

        if not seen_data and is_header_like(values):
            header_candidates.append((row_number, values))
            continue

        header_rows = [candidate_values for _, candidate_values in header_candidates]
        headers = flatten_headers(header_rows, len(values))
        chunks.extend(spreadsheet_row_chunks(start_index + len(chunks), section, sheet_name, row_number, context, values, headers))
        seen_data = True

    if not chunks and len(header_candidates) > 1:
        base_header = header_candidates[0][1]
        for row_number, values in header_candidates[1:]:
            headers = flatten_headers([base_header], len(values))
            chunks.extend(spreadsheet_row_chunks(start_index + len(chunks), section, sheet_name, row_number, context, values, headers))

    if not chunks and context:
        content = "\n".join(context)
        chunks.append(spreadsheet_chunk(start_index, section, sheet_name, 1, [], sheet_name, content, context))

    return chunks


def spreadsheet_row_chunks(
    index: int,
    section: str,
    sheet_name: str,
    row_number: int,
    context: list[str],
    values: list[str],
    headers: list[str],
) -> list[Chunk]:
    content = row_to_text(values, headers)
    heading = row_heading(values, headers, context)
    if len(tokenize(content)) <= settings.chunk_target_tokens:
        return [spreadsheet_chunk(index, section, sheet_name, row_number, context, heading, content, values, headers)]

    key_lines = []
    for column_index, value in enumerate(values):
        if value and len(value) <= 100:
            header = headers[column_index] if column_index < len(headers) else f"Column {column_index + 1}"
            key_lines.append(f"{header}: {value}")
        if len(key_lines) >= 2:
            break

    chunks = []
    for column_index, value in enumerate(values):
        if not value:
            continue
        header = headers[column_index] if column_index < len(headers) else f"Column {column_index + 1}"
        if len(value) <= 100 and key_lines:
            continue
        parts = split_text_by_tokens(value, settings.chunk_target_tokens)
        for part_index, part in enumerate(parts):
            suffix = f" part {part_index + 1}" if len(parts) > 1 else ""
            cell_content = "\n".join([*key_lines, f"{header}: {part}"]).strip()
            chunks.append(
                spreadsheet_chunk(
                    index + len(chunks),
                    section,
                    sheet_name,
                    row_number,
                    context,
                    f"{heading} / {header}{suffix}" if heading else f"{header}{suffix}",
                    cell_content,
                    values,
                    headers,
                )
            )
    return chunks or [spreadsheet_chunk(index, section, sheet_name, row_number, context, heading, content, values, headers)]


def split_text_by_tokens(value: str, target_tokens: int) -> list[str]:
    words = tokenize_raw(value)
    if len(words) <= target_tokens:
        return [value]
    parts = []
    step = max(target_tokens - min(settings.chunk_overlap_tokens, 32), 80)
    for start in range(0, len(words), step):
        segment = words[start : start + target_tokens]
        if segment:
            parts.append(" ".join(segment))
    return parts


def spreadsheet_chunk(
    index: int,
    section: str,
    sheet_name: str,
    row_number: int,
    context: list[str],
    heading: str,
    content: str,
    values: list[str] | None = None,
    headers: list[str] | None = None,
) -> Chunk:
    context_lines = [f"Ngữ cảnh: {item}" for item in context[-3:]]
    body = "\n".join([*context_lines, content]).strip()
    resolved_heading = heading or (context[-1] if context else f"{sheet_name} dòng {row_number}")
    return Chunk(
        chunk_index=index,
        section=section,
        heading=resolved_heading[:180],
        content=body,
        token_count=len(tokenize(body)),
        metadata={
            "sheet_name": sheet_name,
            "row_number": row_number,
            "headers": headers or [],
            "row_values": values or [],
            "source_type": "spreadsheet",
        },
    )


def row_to_text(values: list[str], headers: list[str]) -> str:
    pairs = []
    for index, value in enumerate(values):
        if not value:
            continue
        header = headers[index] if index < len(headers) and headers[index] else f"Column {index + 1}"
        pairs.append(f"{header}: {value}")
    return "\n".join(pairs)


def row_heading(values: list[str], headers: list[str], context: list[str]) -> str:
    for index, value in enumerate(values):
        if value and len(value) <= 80:
            header = headers[index] if index < len(headers) else ""
            if header:
                return f"{header}: {value}"
            return value
    return context[-1] if context else ""


def flatten_headers(header_rows: list[list[str]], width: int) -> list[str]:
    if not header_rows:
        return [f"Column {index + 1}" for index in range(width)]

    filled_rows = [fill_horizontal(row, width) for row in header_rows]
    output = []
    for column in range(width):
        parts = []
        for row in filled_rows:
            if column < len(row) and row[column] and row[column] not in parts:
                parts.append(row[column])
        output.append(" / ".join(parts) if parts else f"Column {column + 1}")
    return output


def fill_horizontal(values: list[str], width: int) -> list[str]:
    output = values[:width] + [""] * max(0, width - len(values))
    last = ""
    for index, value in enumerate(output):
        if value:
            last = value
        elif last:
            output[index] = last
    return output


def is_header_like(values: list[str]) -> bool:
    non_empty = [value for value in values if value]
    if not non_empty:
        return False
    if any(len(value) > 120 for value in non_empty):
        return False
    return True


def cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize_cell_text(str(value))


def normalize_cell_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()


def trim_trailing_empty(values: list[str]) -> list[str]:
    output = list(values)
    while output and not output[-1]:
        output.pop()
    return output


def reindex_chunks(chunks: list[Chunk]) -> list[Chunk]:
    return [
        Chunk(
            chunk_index=index,
            section=chunk.section,
            heading=chunk.heading,
            content=chunk.content,
            token_count=chunk.token_count,
            metadata=chunk.metadata,
        )
        for index, chunk in enumerate(chunks)
    ]


def ensure_full_sop_layer(
    chunks: list[Chunk],
    raw_text: str,
    filename: str,
    source_type: str,
    document_type: str,
) -> list[Chunk]:
    has_document_layer = any(
        chunk.section == "full_sop"
        or chunk.metadata.get("unit_type") == "full_sop"
        or chunk.metadata.get("retrieval_scope") == "document"
        for chunk in chunks
    )
    if has_document_layer:
        return reindex_chunks(chunks)

    content = normalize_cell_text(raw_text).strip()
    if not content:
        return reindex_chunks(chunks)
    full_content = content[:30000]
    if len(content) > len(full_content):
        full_content += "\n\n[Nội dung gốc dài hơn 30.000 ký tự và đã được rút gọn trong full SOP preview. Atomic units vẫn dùng các chunk bên dưới.]"

    document_chunk = Chunk(
        chunk_index=0,
        section="full_sop",
        heading=path_safe_title(filename),
        content=full_content,
        token_count=len(tokenize(full_content)),
        metadata={
            "unit_type": "full_sop",
            "retrieval_scope": "document",
            "source_type": source_type,
            "document_type": document_type,
            "source_filename": filename,
            "confidence": 0.72,
            "review_status": "needs_review",
            "source_refs": [default_source_ref(filename, source_type, full_content)],
            "source_ref_quality": default_source_ref_quality(filename),
            "production_ready_source_refs": default_source_ref_quality(filename) != "page_only",
            "source_ref_acknowledged": False if default_source_ref_quality(filename) == "page_only" else True,
        },
    )
    return reindex_chunks([document_chunk, *chunks])


def path_safe_title(filename: str) -> str:
    title = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return title.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:180] or "Full SOP"


def default_source_ref(filename: str, source_type: str, content: str) -> dict[str, Any]:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        return {"source_type": "excel", "source_file": filename, "sheet": "unknown", "row_start": 1, "row_end": 1}
    if lower.endswith(".pdf"):
        return {"source_type": "pdf_diagram" if source_type == "diagram_pdf" else "pdf", "source_file": filename, "page": 1, "bbox": []}
    if lower.endswith(".docx"):
        return {"source_type": "docx", "source_file": filename, "paragraph_index": 0}
    line_count = max(1, content.count("\n") + 1)
    return {"source_type": source_type or "text", "source_file": filename, "line_start": 1, "line_end": line_count}


def default_source_ref_quality(filename: str) -> str:
    return "page_only" if filename.lower().endswith(".pdf") else "structured"


def workflow_units_to_chunks(units: list[dict[str, Any]], raw_text: str, filename: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    effective_from = extract_effective_date(raw_text)
    workflow_id = workflow_identifier(filename, raw_text)
    for index, unit in enumerate(units):
        content = normalize_cell_text(str(unit.get("content") or ""))
        if not content:
            continue
        unit_type = slugify(str(unit.get("unit_type") or "workflow_step")) or "workflow_step"
        metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                section=unit_type,
                heading=(str(unit.get("title") or vietnamese_unit_title(unit_type)).strip() or vietnamese_unit_title(unit_type))[:180],
                content=content,
                token_count=len(tokenize(content)),
                metadata={
                    "unit_type": unit_type,
                    "workflow_id": workflow_id,
                    "source_type": "diagram_pdf",
                    "source_page": metadata.get("source_page") or metadata.get("page_number") or 1,
                    "page_number": metadata.get("page_number") or metadata.get("source_page") or 1,
                    "source_ref_quality": metadata.get("source_ref_quality") or "page_only",
                    "production_ready_source_refs": metadata.get("production_ready_source_refs") if "production_ready_source_refs" in metadata else False,
                    "source_ref_acknowledged": metadata.get("source_ref_acknowledged") is True,
                    "effective_from": metadata.get("effective_from") or effective_from,
                    "confidence": unit.get("confidence", metadata.get("confidence", 0.74)),
                    **metadata,
                    "retrieval_scope": metadata.get("retrieval_scope") or ("document" if unit_type == "full_sop" else "unit"),
                },
            )
        )
    return chunks


def ai_units_to_chunks(units: list[dict[str, Any]], filename: str, source_type: str, document_type: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for unit in units:
        content = normalize_cell_text(str(unit.get("content") or ""))
        if not content:
            continue
        metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
        unit_type = slugify(str(unit.get("unit_type") or metadata.get("unit_type") or "text_section")) or "text_section"
        confidence = unit.get("confidence", metadata.get("confidence", 0.72))
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.72
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                section=unit_type,
                heading=(str(unit.get("title") or vietnamese_unit_title(unit_type)).strip() or vietnamese_unit_title(unit_type))[:180],
                content=content,
                token_count=len(tokenize(content)),
                metadata={
                    "unit_type": unit_type,
                    "source_type": source_type,
                    "document_type": document_type,
                    "source_filename": filename,
                    "confidence": max(0.0, min(confidence_value, 1.0)),
                    "retrieval_scope": metadata.get("retrieval_scope") or ("document" if unit_type == "full_sop" else "unit"),
                    **metadata,
                },
            )
        )
    return chunks


def vietnamese_unit_title(unit_type: str) -> str:
    titles = {
        "workflow_overview": "Tổng quan quy trình",
        "workflow_graph": "Workflow graph",
        "verification_dependency": "Tài liệu xác minh liên quan",
        "workflow_step": "Bước xử lý",
        "decision_point": "Điểm quyết định",
        "decision_rule": "Quy tắc quyết định",
        "sla_rule": "Quy định SLA",
        "escalation_rule": "Quy định chuyển xử lý",
        "case_creation_rule": "Quy định tạo case",
        "handoff_rule": "Quy định handoff",
        "operational_instruction": "Hướng dẫn thao tác",
        "routing_rule": "Quy định routing",
        "macro_script": "Script phản hồi",
        "operational_note": "Lưu ý vận hành",
        "security_note": "Lưu ý bảo mật",
        "related_document": "Tài liệu liên quan",
    }
    return titles.get(unit_type, "Đơn vị trích xuất cần review")


def extract_effective_date(text: str) -> str:
    match = re.search(r"(?:Áp dụng từ|Ap dung tu)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text, re.IGNORECASE)
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def workflow_identifier(filename: str, raw_text: str) -> str:
    return slugify(filename)[:80] or "workflow"

def chunk_text(text: str, target_tokens: int | None = None, overlap_tokens: int | None = None) -> list[Chunk]:
    target = target_tokens or settings.chunk_target_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens
    paragraphs = split_paragraphs(text)

    chunks: list[Chunk] = []
    current_words: list[str] = []
    current_heading = ""
    current_section = "body"

    def flush() -> None:
        nonlocal current_words
        if not current_words:
            return
        content = " ".join(current_words).strip()
        if content:
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    section=current_section,
                    heading=current_heading,
                    content=content,
                    token_count=len(tokenize(content)),
                )
            )
        current_words = current_words[-overlap:] if overlap > 0 else []

    for paragraph in paragraphs:
        heading = detect_heading(paragraph)
        if heading:
            flush()
            current_heading = heading
            current_section = slugify(heading)[:80] or "body"
            continue

        words = tokenize_raw(paragraph)
        if not words:
            continue

        if len(current_words) + len(words) > target:
            flush()
        current_words.extend(words)

        while len(current_words) >= target + overlap:
            flush()

    flush()
    return chunks


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_query(query: str, synonym_groups: list[dict] | None = None) -> str:
    normalized, _, _ = expand_query(query, synonym_groups)
    return normalized


def expand_query(query: str, synonym_groups: list[dict] | None = None) -> tuple[str, list[str], list[dict[str, Any]]]:
    normalized = normalize_phrase(query)
    expansions: list[str] = []
    matched_groups: list[dict[str, Any]] = []

    for group in synonym_groups or []:
        synonym_type = str(group.get("synonym_type") or "")
        if synonym_type == "placeholder":
            continue

        canonical = normalize_phrase(str(group.get("canonical_key") or ""))
        terms = unique_phrases([normalize_phrase(str(term.get("term") if isinstance(term, dict) else term)) for term in group.get("terms", [])])
        matched_terms = [term for term in terms if phrase_in_query(term, normalized)]
        matched_term = bool(matched_terms)
        matched_canonical = bool(canonical and phrase_in_query(canonical, normalized))

        if synonym_type == "regular" and (matched_term or matched_canonical):
            expansions.extend([canonical, *terms])
            matched_groups.append(explain_synonym_match(group, matched_terms, matched_canonical))
        elif synonym_type in {"one_way", "typo_correction"} and matched_term:
            expansions.append(canonical)
            matched_groups.append(explain_synonym_match(group, matched_terms, matched_canonical))

    normalized_query = join_unique([normalized, *expansions])
    return normalized_query, unique_phrases(expansions), matched_groups


def explain_synonym_match(group: dict, matched_terms: list[str], matched_canonical: bool) -> dict[str, Any]:
    return {
        "group_id": str(group.get("id") or ""),
        "canonical_key": str(group.get("canonical_key") or ""),
        "synonym_type": str(group.get("synonym_type") or ""),
        "domain": str(group.get("domain") or ""),
        "audience": str(group.get("audience") or ""),
        "matched_terms": matched_terms,
        "matched_canonical": matched_canonical,
    }


def normalize_phrase(text: str) -> str:
    return " ".join(tokenize(text.replace("_", " ")))


def phrase_in_query(phrase: str, query: str) -> bool:
    if not phrase or not query:
        return False
    return f" {phrase} " in f" {query} "


def join_unique(values: list[str]) -> str:
    seen = set()
    output = []
    for value in values:
        normalized = normalize_phrase(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return " ".join(output).strip()


def unique_phrases(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        normalized = normalize_phrase(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def tokenize(text: str) -> list[str]:
    text = text.replace("_", " ")
    return [normalize_token(match.group(0)) for match in WORD_RE.finditer(text) if normalize_token(match.group(0))]


def tokenize_raw(text: str) -> list[str]:
    return [match.group(0) for match in WORD_RE.finditer(text)]


def normalize_token(token: str) -> str:
    token = strip_accents(unicodedata.normalize("NFKC", token).lower())
    token = token.replace("_", " ")
    token = re.sub(r"[^\w]+", "", token, flags=re.UNICODE)
    return token


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.replace("đ", "d").replace("Đ", "D")


def normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line)


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n{1,}", text)
    return [part.strip() for part in parts if part.strip()]


def detect_heading(paragraph: str) -> str:
    if len(paragraph) > 120:
        return ""
    if re.match(r"^\s*[0-9]+[\.)]\s+", paragraph):
        return ""
    match = HEADING_RE.match(paragraph)
    if match:
        return match.group(2).strip()
    if paragraph.endswith(":") and 8 <= len(paragraph) <= 90:
        return paragraph[:-1].strip()
    return ""


def slugify(value: str) -> str:
    tokens = tokenize(value)
    return "_".join(tokens)
