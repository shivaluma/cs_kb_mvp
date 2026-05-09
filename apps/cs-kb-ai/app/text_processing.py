from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from docx import Document as DocxDocument
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


def extract_text(filename: str, content_type: str, data: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lower_name = filename.lower()

    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"file_too_large:{settings.max_upload_bytes}")

    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        text = extract_pdf_text(data)
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


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for index, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"\n\n[page {index + 1}]\n{page_text}")
    return "\n".join(pages)


def extract_docx_text(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    blocks = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))
    return "\n".join(blocks)


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
