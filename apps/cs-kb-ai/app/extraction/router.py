from __future__ import annotations

from typing import Any


def extraction_profile_for_file(filename: str, content_type: str, accuracy_mode: str = "balanced") -> dict[str, Any]:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        extractors = ["openpyxl_workbook_graph"]
    elif lower.endswith(".docx"):
        extractors = ["docx_ooxml_structure"]
    elif lower.endswith(".pdf") or content_type == "application/pdf":
        extractors = ["pdf_text", "pdf_visual_layout"]
    elif lower.endswith(".md") or content_type in {"text/markdown", "text/x-markdown"}:
        extractors = ["markdown_ast"]
    else:
        extractors = ["plain_text_line_parser"]
    if accuracy_mode == "max" and "pdf_visual_layout" in extractors:
        extractors.append("multimodal_layout_oracle")
    return {"accuracy_mode": accuracy_mode, "extractors": extractors}
