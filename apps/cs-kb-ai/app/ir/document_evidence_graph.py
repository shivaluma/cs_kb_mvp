from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.ir.provenance import IR_PARSER_VERSION, artifact_id_for, provenance_for_block, source_locator_for_ref
from app.ir.schema import (
    Container,
    DocumentArtifact,
    DocumentEvidenceGraph,
    Provenance,
    Relation,
    SourceElement,
    excerpt_hash,
)


def build_document_evidence_graph(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    raw_text: str,
    raw_context: dict[str, Any],
    blocks: list[dict[str, Any]],
    classification: Any | None,
) -> DocumentEvidenceGraph:
    artifact = DocumentArtifact(
        artifact_id=artifact_id_for(filename, data),
        sha256=hashlib.sha256(data or b"").hexdigest(),
        mime_type=content_type,
        extension=Path(filename).suffix.lower(),
        original_filename=filename,
        parser_versions={"document_evidence_graph": IR_PARSER_VERSION},
    )
    document_container = Container(
        container_id="document",
        kind="document",
        metadata={
            "filename": filename,
            "document_type": getattr(classification, "document_type", None),
            "source_type": getattr(classification, "source_type", None),
        },
    )
    graph = DocumentEvidenceGraph(
        artifact=artifact,
        containers=[document_container],
        metadata={
            "filename": filename,
            "content_type": content_type,
            "document_type": getattr(classification, "document_type", ""),
            "source_type": getattr(classification, "source_type", ""),
        },
    )

    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")) or "sheets" in raw_context:
        _add_spreadsheet_elements(graph, filename, content_type, raw_context)
    elif lower.endswith(".md") or content_type in {"text/markdown", "text/x-markdown"}:
        _add_markdown_elements(graph, filename, content_type, raw_text)
    elif isinstance(raw_context.get("docx_blocks"), list):
        _add_block_elements(graph, filename, content_type, raw_context["docx_blocks"], default_kind="paragraph")
    else:
        _add_block_elements(graph, filename, content_type, blocks, default_kind="text")

    visual_layout = raw_context.get("visual_layout") if isinstance(raw_context.get("visual_layout"), dict) else {}
    if visual_layout:
        _add_visual_layout_elements(graph, filename, visual_layout)

    _add_precedence_relations(graph)
    return graph


def _add_block_elements(
    graph: DocumentEvidenceGraph,
    filename: str,
    content_type: str,
    blocks: list[dict[str, Any]],
    *,
    default_kind: str,
) -> None:
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or block.get("content") or "").strip()
        if not text:
            continue
        kind = _element_kind_from_block(block, default_kind)
        element_id = str(block.get("block_id") or f"element_{len(graph.source_elements) + 1}")
        provenance = provenance_for_block(filename, content_type, {**block, "text": text})
        locator = provenance.source_locator
        graph.source_elements.append(
            SourceElement(
                element_id=element_id,
                kind=kind,
                container_id="document",
                text=text,
                bbox=_bbox(locator.get("bbox")),
                page_number=_int(locator.get("page")),
                sheet_name=locator.get("sheet") or locator.get("sheet_name"),
                row_index=_int(locator.get("row_index") or locator.get("row_start")),
                confidence=float(block.get("confidence") or 1.0),
                provenance=provenance,
                metadata={
                    "source_refs": block.get("source_refs") if isinstance(block.get("source_refs"), list) else [_source_ref_from_locator(locator)],
                    "section_path": block.get("section_path") if isinstance(block.get("section_path"), list) else [],
                    "order_index": index,
                    "block_type": block.get("type") or block.get("block_type") or default_kind,
                },
            )
        )


def _add_markdown_elements(graph: DocumentEvidenceGraph, filename: str, content_type: str, raw_text: str) -> None:
    section_stack: list[tuple[int, str]] = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        text = line.rstrip()
        if not text.strip():
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", text)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            section_stack = [(item_level, item_title) for item_level, item_title in section_stack if item_level < level]
            section_stack.append((level, title))
            kind = "heading"
        else:
            kind = "list_item" if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", text) else "paragraph"
        section_path = [title for _level, title in section_stack]
        block = {
            "type": "markdown",
            "text": text.strip(),
            "line_start": line_number,
            "line_end": line_number,
        }
        graph.source_elements.append(
            SourceElement(
                element_id=f"md_line_{line_number}",
                kind=kind,
                container_id="document",
                text=text.strip(),
                confidence=1.0,
                provenance=provenance_for_block(filename, content_type, block, parser_name="markdown_ast_parser"),
                metadata={
                    "ast_path": section_path,
                    "section_path": section_path,
                    "source_refs": [{"source_type": "markdown", "source_file": filename, "line_start": line_number, "line_end": line_number}],
                },
            )
        )


def _add_spreadsheet_elements(graph: DocumentEvidenceGraph, filename: str, content_type: str, raw_context: dict[str, Any]) -> None:
    sheets = raw_context.get("sheets") if isinstance(raw_context.get("sheets"), list) else []
    for sheet_index, sheet in enumerate(sheets):
        if not isinstance(sheet, (list, tuple)) or len(sheet) < 2:
            continue
        sheet_name = str(sheet[0])
        rows = sheet[1] if isinstance(sheet[1], list) else []
        container_id = f"sheet_{_slug(sheet_name) or sheet_index + 1}"
        graph.containers.append(
            Container(
                container_id=container_id,
                kind="sheet",
                parent_id="document",
                sheet_name=sheet_name,
                order_index=sheet_index,
                metadata={"title": sheet_name},
            )
        )
        for row_position, row in enumerate(rows):
            row_number, values = _spreadsheet_row_parts(row, row_position + 1)
            value_texts = [str(value).strip() for value in values if str(value).strip()]
            if not value_texts:
                continue
            row_text = " | ".join(value_texts)
            row_ref = {"source_type": "excel", "source_file": filename, "sheet": sheet_name, "row_start": row_number, "row_end": row_number}
            row_element_id = f"{container_id}_row_{row_number}"
            graph.source_elements.append(
                SourceElement(
                    element_id=row_element_id,
                    kind="table_row",
                    container_id=container_id,
                    text=row_text,
                    sheet_name=sheet_name,
                    row_index=row_number,
                    confidence=1.0,
                    provenance=Provenance(
                        parser_name="openpyxl",
                        parser_version=IR_PARSER_VERSION,
                        extraction_method="deterministic",
                        source_locator=row_ref,
                        raw_excerpt_hash=excerpt_hash(row_text),
                    ),
                    metadata={"source_refs": [row_ref], "row_values": values},
                )
            )
            for col_index, value in enumerate(values, start=1):
                value_text = str(value).strip()
                if not value_text:
                    continue
                cell_ref = f"{_excel_col(col_index)}{row_number}"
                cell_locator = {**row_ref, "cell_ref": cell_ref, "col_index": col_index}
                graph.source_elements.append(
                    SourceElement(
                        element_id=f"{container_id}_{cell_ref}",
                        kind="spreadsheet_cell",
                        container_id=container_id,
                        text=value_text,
                        value=value,
                        normalized_value=value_text,
                        sheet_name=sheet_name,
                        cell_ref=cell_ref,
                        row_index=row_number,
                        col_index=col_index,
                        confidence=1.0,
                        provenance=Provenance(
                            parser_name="openpyxl",
                            parser_version=IR_PARSER_VERSION,
                            extraction_method="deterministic",
                            source_locator=cell_locator,
                            raw_excerpt_hash=excerpt_hash(value_text),
                        ),
                        metadata={"source_refs": [cell_locator]},
                    )
                )
                graph.relations.append(
                    Relation(
                        relation_id=f"contains_{row_element_id}_{cell_ref}",
                        kind="contains",
                        source_id=row_element_id,
                        target_id=f"{container_id}_{cell_ref}",
                        provenance=Provenance(
                            parser_name="openpyxl",
                            parser_version=IR_PARSER_VERSION,
                            extraction_method="deterministic",
                            source_locator=cell_locator,
                            raw_excerpt_hash=excerpt_hash(value_text),
                        ),
                    )
                )


def _add_visual_layout_elements(graph: DocumentEvidenceGraph, filename: str, visual_layout: dict[str, Any]) -> None:
    pages = visual_layout.get("pages") if isinstance(visual_layout.get("pages"), list) else []
    node_id_to_element: dict[str, str] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 1)
        page_container_id = f"page_{page_number}"
        graph.containers.append(
            Container(
                container_id=page_container_id,
                kind="page",
                parent_id="document",
                page_number=page_number,
                order_index=page_number,
                metadata={"image_size": page.get("image_size") or []},
            )
        )
        graph_candidate = page.get("graph_candidate") if isinstance(page.get("graph_candidate"), dict) else {}
        nodes = _graph_items(graph_candidate, "nodes", "node_candidates")
        for index, node in enumerate(nodes):
            node_id = str(node.get("id") or node.get("node_id") or f"page_{page_number}_node_{index + 1}")
            text = str(node.get("source_text") or node.get("text") or node.get("title") or node_id).strip()
            bbox = _bbox(node.get("bbox"))
            source_ref = {"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": bbox}
            element_id = f"graph_node_{_slug(node_id) or index + 1}"
            node_id_to_element[node_id] = element_id
            graph.source_elements.append(
                SourceElement(
                    element_id=element_id,
                    kind="graph_node",
                    container_id=page_container_id,
                    text=text,
                    bbox=bbox,
                    page_number=page_number,
                    confidence=float(node.get("confidence") or 0.75),
                    provenance=Provenance(
                        parser_name="pdf_visual_layout",
                        parser_version=IR_PARSER_VERSION,
                        extraction_method="visual_ai" if node.get("model") else "deterministic",
                        source_locator=source_ref,
                        raw_excerpt_hash=excerpt_hash(text),
                    ),
                    metadata={
                        "node_id": node_id,
                        "step_code": node.get("step_code"),
                        "node_type": node.get("node_type") or node.get("type"),
                        "source_refs": [source_ref],
                    },
                )
            )
        edges = _graph_items(graph_candidate, "edges", "edge_candidates")
        for index, edge in enumerate(edges):
            from_node = str(edge.get("from_node") or edge.get("from_node_id") or edge.get("from") or "").strip()
            to_node = str(edge.get("to_node") or edge.get("to_node_id") or edge.get("to") or "").strip()
            condition = str(edge.get("condition") or edge.get("label_text") or "next").strip().lower() or "next"
            text = str(edge.get("source_text") or edge.get("text") or f"{from_node} --{condition}--> {to_node}").strip()
            bbox = _bbox(edge.get("bbox"))
            source_refs = edge.get("source_refs") if isinstance(edge.get("source_refs"), list) else []
            if not source_refs and bbox:
                source_refs = [{"source_type": "pdf_diagram", "source_file": filename, "page": page_number, "bbox": bbox}]
            locator = source_locator_for_ref(source_refs[0]) if source_refs and isinstance(source_refs[0], dict) else {
                "source_type": "pdf_diagram",
                "source_file": filename,
                "page": page_number,
                "bbox": bbox,
            }
            element_id = f"graph_edge_{page_number}_{index + 1}"
            graph.source_elements.append(
                SourceElement(
                    element_id=element_id,
                    kind="graph_edge",
                    container_id=page_container_id,
                    text=text,
                    bbox=bbox,
                    page_number=page_number,
                    confidence=float(edge.get("confidence") or (0.72 if source_refs else 0.45)),
                    provenance=Provenance(
                        parser_name="pdf_visual_layout",
                        parser_version=IR_PARSER_VERSION,
                        extraction_method="visual_ai" if edge.get("model") else "deterministic",
                        source_locator=locator,
                        raw_excerpt_hash=excerpt_hash(text),
                    ),
                    metadata={
                        "from_node_id": from_node,
                        "to_node_id": to_node,
                        "condition": condition,
                        "source_refs": source_refs,
                        "missing_edge_evidence": not bool(source_refs),
                    },
                )
            )
            if from_node in node_id_to_element and to_node in node_id_to_element:
                graph.relations.append(
                    Relation(
                        relation_id=f"flows_to_{element_id}",
                        kind="flows_to",
                        source_id=node_id_to_element[from_node],
                        target_id=node_id_to_element[to_node],
                        confidence=float(edge.get("confidence") or (0.72 if source_refs else 0.45)),
                        provenance=Provenance(
                            parser_name="pdf_visual_layout",
                            parser_version=IR_PARSER_VERSION,
                            extraction_method="deterministic",
                            source_locator=locator,
                            raw_excerpt_hash=excerpt_hash(text),
                        ),
                        metadata={"edge_element_id": element_id, "condition": condition, "missing_edge_evidence": not bool(source_refs)},
                    )
                )


def _add_precedence_relations(graph: DocumentEvidenceGraph) -> None:
    by_container: dict[str, list[SourceElement]] = {}
    for element in graph.source_elements:
        if element.kind in {"spreadsheet_cell", "graph_edge"}:
            continue
        by_container.setdefault(element.container_id, []).append(element)
    for elements in by_container.values():
        for left, right in zip(elements, elements[1:]):
            graph.relations.append(
                Relation(
                    relation_id=f"precedes_{left.element_id}_{right.element_id}",
                    kind="precedes",
                    source_id=left.element_id,
                    target_id=right.element_id,
                    provenance=left.provenance,
                )
            )


def _element_kind_from_block(block: dict[str, Any], default_kind: str) -> str:
    block_type = str(block.get("type") or block.get("block_type") or "").lower()
    if "heading" in block_type:
        return "heading"
    if "table_cell" in block_type:
        return "table_cell"
    if "table_row" in block_type:
        return "table_row"
    if "table" in block_type:
        return "table"
    if "list" in block_type:
        return "list_item"
    if "paragraph" in block_type:
        return "paragraph"
    if "pdf_line" in block_type or "line" == block_type:
        return "text"
    return default_kind


def _source_ref_from_locator(locator: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in locator.items() if value not in (None, "", [])}


def _graph_items(graph_candidate: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = graph_candidate.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _spreadsheet_row_parts(row: Any, fallback_number: int) -> tuple[int, list[Any]]:
    if isinstance(row, (list, tuple)):
        if len(row) == 2 and isinstance(row[0], int) and isinstance(row[1], list):
            return row[0], row[1]
        return fallback_number, list(row)
    return fallback_number, [row]


def _excel_col(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result or "A"


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) < 4:
        return None
    output: list[float] = []
    for item in value[:4]:
        try:
            output.append(float(item))
        except (TypeError, ValueError):
            return None
    return output


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
