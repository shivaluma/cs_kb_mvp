from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.schemas import WorkflowExtractionPayload


STEP_CODE_RE = re.compile(r"(?<![\d/])(?:bước\s*)?(\d{1,2}(?:\.\d{1,2})?)(?=[.)]?\s)", re.IGNORECASE)
LINE_STEP_CODE_RE = re.compile(r"^\s*(?:yes|no|có|không)?\s*(?:bước\s*)?(\d{1,2}(?:\.\d{1,2})?)(?=[.)]?\s)", re.IGNORECASE)
MULTI_STEP_NODE_BOUNDARY_RE = re.compile(r"(?im)^\s*(?:yes|no|có|không)?\s*(?:bước\s*)?(\d{1,2}(?:\.\d{1,2})?)(?=[.)]?\s)")
NOTE_MARKER_RE = re.compile(r"^\s*(?:\(\*+\)|\([a-z]\)|lưu ý|luu y|ghi chú|ghi chu|note|quy định audit|quy dinh audit)\b", re.IGNORECASE)
VALID_EDGE_CONDITIONS = {"yes", "no", "next", "timeout", "escalation", "fallback", "handoff", "return", "retry"}
EXTERNAL_CONTINUATION_STATES = {"continues_with_related_sop"}
WORKFLOW_LINE_HINT_RE = re.compile(
    r"\b("
    r"cs|kh|tx|khách hàng|khach hang|tài xế|tai xe|kiểm tra|kiem tra|cung cấp|cung cap|xử lý|xu ly|"
    r"phản hồi|phan hoi|chuyển|chuyen|gọi|goi|liên hệ|lien he|hướng dẫn|huong dan|lấy|lay|gửi|gui|"
    r"case|email|trip|order|sđt|sdt|queue|status|resolved|có|co|không|khong"
    r")\b|\?",
    re.IGNORECASE,
)


def compile_workflow_v3_payload(
    *,
    filename: str,
    raw_text: str,
    transcription: dict[str, Any],
    visual_context: dict[str, Any] | None = None,
) -> tuple[WorkflowExtractionPayload | None, dict[str, Any], dict[str, Any]]:
    canvas = normalize_canvas_transcription(transcription)
    visible_step_codes = visible_step_codes_from_sources(raw_text, canvas, visual_context or {})
    nodes, node_lookup, node_conflicts = compile_canvas_nodes(filename, canvas)
    title_hint = str(transcription.get("title") or transcription.get("document_metadata", {}).get("title") or filename)
    node_conflicts.extend(ensure_boundary_nodes(filename, raw_text, title_hint, canvas, nodes, node_lookup))
    annotations = compile_canvas_annotations(filename, canvas, node_lookup)
    annotation_conflicts = attach_orphan_annotations_to_nearest_node(annotations, nodes)
    relations = compile_canvas_relations(filename, canvas)
    edges, uncertain_edges, edge_conflicts, expected_edges = compile_canvas_edges(filename, canvas, node_lookup)
    edge_conflicts.extend(ensure_boundary_and_terminal_edges(filename, nodes, edges, uncertain_edges))

    fidelity_report = workflow_v3_fidelity_report(
        nodes=nodes,
        annotations=annotations,
        edges=edges,
        uncertain_edges=uncertain_edges,
        visible_step_codes=visible_step_codes,
        expected_edges=expected_edges,
        detector_conflicts=[*node_conflicts, *annotation_conflicts, *edge_conflicts],
    )
    repair_report = workflow_graph_repair_report(
        nodes=nodes,
        annotations=annotations,
        relations=relations,
        edges=edges,
        uncertain_edges=uncertain_edges,
        repair_events=[*node_conflicts, *annotation_conflicts, *edge_conflicts],
        fidelity_report=fidelity_report,
    )
    graph_confidence = fidelity_report["fidelity_score"]
    graph = {
        "workflow_id": normalized_key(transcription.get("workflow_id") or transcription.get("title") or filename) or "workflow_graph",
        "title": str(transcription.get("title") or transcription.get("document_metadata", {}).get("title") or filename.rsplit(".", 1)[0])[:240],
        "start_node_id": first_start_node_id(nodes),
        "lanes": workflow_lanes(nodes, canvas),
        "nodes": nodes,
        "edges": edges,
        "annotations": annotations,
        "warnings": [annotation for annotation in annotations if annotation.get("type") in {"warning", "audit_rule"}],
        "uncertain_edges": uncertain_edges,
        "graph_confidence": graph_confidence,
        "requires_human_review": True,
        "review_reason": workflow_v3_review_reason(fidelity_report),
        "topology_source": "workflow_v3_canvas_transcription",
        "topology_review_required": True,
        "visible_step_codes": fidelity_report["visible_step_codes"],
        "covered_step_codes": fidelity_report["covered_step_codes"],
        "missing_step_codes": fidelity_report["missing_step_codes"],
        "fidelity_score": fidelity_report["fidelity_score"],
        "detector_conflicts": fidelity_report["detector_conflicts"],
        "validation_errors": fidelity_report["blockers"],
        "repair_applied": repair_report["repair_applied"],
        "repair_report": repair_report,
        "graph_fidelity_score": fidelity_report["fidelity_score"],
        "decision_edges_review_required": repair_report["decision_edges_review_required"],
        "missing_terminal_edges": repair_report["missing_terminal_edges"],
        "orphan_annotations": repair_report["orphan_annotations"],
        "unresolved_relations": repair_report["unresolved_relations"],
        "source_refs": [page_source_ref(filename, canvas)],
    }

    metadata = transcription.get("document_metadata") if isinstance(transcription.get("document_metadata"), dict) else {}
    document_metadata = {
        **metadata,
        "document_type": "workflow_diagram",
        "extraction_strategy": "workflow_v3_graph_primary",
        "requires_human_review": True,
        "visible_step_codes": fidelity_report["visible_step_codes"],
        "missing_step_codes": fidelity_report["missing_step_codes"],
    }
    full_sop_content = workflow_v3_full_sop_content(graph, annotations, relations)
    payload_dict = {
        "document_metadata": document_metadata,
        "full_sop": {
            "unit_type": "full_sop",
            "title": graph["title"],
            "content": full_sop_content,
            "confidence": graph_confidence,
            "metadata": {
                "retrieval_scope": "document",
                "workflow_v3": True,
                "fidelity_report": fidelity_report,
                "repair_report": repair_report,
            },
            "source_refs": graph["source_refs"],
        },
        "workflow_graph": graph,
        "atomic_units": workflow_v3_atomic_units(graph, annotations, relations, graph_confidence),
        "annotations": annotations,
        "uncertain_edges": uncertain_edges,
        "validation_errors": fidelity_report["blockers"],
        "warnings": fidelity_report["warnings"],
        "search_enrichment": {
            "workflow_v3": True,
            "relations": relations,
            "tags": list(dict.fromkeys(["workflow", "xác minh tài khoản", *metadata_list(metadata.get("tags"))])),
            "actors": metadata_list(metadata.get("actors")),
            "aliases": metadata_list(metadata.get("aliases")),
        },
    }
    try:
        return WorkflowExtractionPayload.model_validate(payload_dict), fidelity_report, canvas
    except Exception as exc:
        fidelity_report = {
            **fidelity_report,
            "blockers": list(dict.fromkeys([*fidelity_report["blockers"], f"workflow_v3_schema_validation_failed:{exc.__class__.__name__}"])),
        }
        return None, fidelity_report, canvas


def normalize_canvas_transcription(transcription: dict[str, Any]) -> dict[str, Any]:
    source = transcription.get("canvas") if isinstance(transcription.get("canvas"), dict) else transcription
    pages = source.get("pages") if isinstance(source.get("pages"), list) else []
    if not pages:
        pages = [
            {
                "page": 1,
                "lanes": source.get("lanes", []),
                "nodes": source.get("nodes", []),
                "edges": source.get("edges") or source.get("arrows") or [],
                "annotations": source.get("annotations") or source.get("notes") or [],
                "relations": source.get("relations") or [],
            }
        ]
    normalized_pages: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        normalized_pages.append(
            {
                "page": int_or_default(page.get("page"), index),
                "image_size": page.get("image_size") if isinstance(page.get("image_size"), list) else [],
                "lanes": list_payload(page.get("lanes")),
                "nodes": list_payload(page.get("nodes")),
                "edges": list_payload(page.get("edges") or page.get("arrows") or page.get("connectors")),
                "annotations": list_payload(page.get("annotations") or page.get("notes")),
                "relations": list_payload(page.get("relations")),
                "warnings": [str(item) for item in list_payload(page.get("warnings"))],
            }
        )
    return {"pages": normalized_pages, "warnings": [str(item) for item in list_payload(source.get("warnings"))]}


def compile_canvas_nodes(filename: str, canvas: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    raw_nodes: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for page in canvas.get("pages", []):
        expanded_nodes = [
            expanded
            for item in page.get("nodes", [])
            if isinstance(item, dict)
            for expanded in split_multi_step_canvas_node(item)
        ]
        for index, item in enumerate(expanded_nodes, start=1):
            if not isinstance(item, dict):
                continue
            text = node_text(item)
            if not text:
                continue
            if is_note_text(text):
                continue
            page_number = int_or_default(item.get("page"), page.get("page") or 1)
            step_code = normalize_step_code(item.get("step_code") or extract_step_code(text))
            node_type = infer_node_type(item, text, step_code)
            node_id = node_identifier(item, node_type, step_code, text)
            node_source_ref = source_ref(filename, page_number, item.get("bbox"))
            lane = str(item.get("lane") or item.get("swimlane") or item.get("actor") or "")
            metadata, metadata_repairs = sanitize_canvas_node_metadata(item.get("metadata"))
            conflicts.extend(metadata_repairs)
            raw_nodes.append(
                {
                    "id": node_id,
                    "source_ids": [str(item.get("id") or "")],
                    "type": node_type,
                    "semantic_node_type": node_type,
                    "step_code": step_code,
                    "shape_kind": str(item.get("shape_kind") or item.get("shape") or item.get("type") or ""),
                    "actor": str(item.get("actor") or lane),
                    "lane_id": str(item.get("lane_id") or normalized_key(lane) or ""),
                    "phase": str(item.get("phase") or ""),
                    "title": node_title(text, step_code, node_type),
                    "content": text,
                    "question": decision_question(text) if node_type == "decision" else "",
                    "terminal_state": normalize_terminal_state(item.get("terminal_state")) or terminal_state_for_text(text),
                    "metadata": metadata,
                    "source_refs": [node_source_ref],
                    "bbox": normalize_bbox(item.get("bbox")),
                    "page": page_number,
                    "attached_annotations": [],
                    "dedupe_status": "unique",
                    "_order": len(raw_nodes) + index,
                }
            )
    merged: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        key = node["step_code"] or semantic_text_key(node["content"])
        if not key:
            key = node["id"]
        existing = merged.get(key)
        if not existing:
            merged[key] = node
            continue
        conflicts.append(f"duplicate_node_merged:{key}")
        existing["dedupe_status"] = "merged"
        existing["source_ids"].extend(node.get("source_ids", []))
        existing["source_refs"] = merge_source_refs(existing.get("source_refs", []), node.get("source_refs", []))
        existing["bbox"] = union_bbox(existing.get("bbox", []), node.get("bbox", []))
        if len(node.get("content", "")) > len(existing.get("content", "")):
            existing["content"] = node["content"]
            existing["title"] = node["title"]
            existing["question"] = node["question"]
        if existing["type"] != "decision" and node["type"] == "decision":
            existing["type"] = "decision"
            existing["semantic_node_type"] = "decision"
            existing["question"] = node["question"] or decision_question(existing["content"])
        if not existing.get("terminal_state") and node.get("terminal_state"):
            existing["terminal_state"] = node["terminal_state"]
    nodes = sorted(merged.values(), key=lambda item: (item.get("page") or 0, item.get("_order") or 0))
    ensure_unique_node_ids(nodes, conflicts)
    lookup: dict[str, str] = {}
    for node in nodes:
        add_lookup_alias(lookup, node["id"], node["id"])
        if node.get("step_code"):
            add_lookup_alias(lookup, str(node["step_code"]), node["id"])
            add_lookup_alias(lookup, f"step_{node['step_code']}", node["id"])
        for source_id in node.get("source_ids", []):
            if not source_id or is_ambiguous_boundary_source_id(source_id):
                continue
            if not add_lookup_alias(lookup, source_id, node["id"]):
                conflicts.append(f"duplicate_source_id_alias_ignored:{source_id}")
            normalized_source_id = normalized_key(source_id)
            if normalized_source_id and not add_lookup_alias(lookup, normalized_source_id, node["id"]):
                conflicts.append(f"duplicate_source_id_alias_ignored:{normalized_source_id}")
        node.pop("_order", None)
        node.pop("source_ids", None)
    add_boundary_aliases(lookup, nodes)
    return nodes, lookup, conflicts


def split_multi_step_canvas_node(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(item.get("text") or item.get("content") or item.get("title") or item.get("label") or "")
    matches = list(MULTI_STEP_NODE_BOUNDARY_RE.finditer(text))
    codes = [normalize_step_code(match.group(1)) for match in matches if normalize_step_code(match.group(1))]
    unique_codes = list(dict.fromkeys(codes))
    if len(unique_codes) < 2:
        return [item]

    output: list[dict[str, Any]] = []
    original_id = str(item.get("id") or "")
    for index, match in enumerate(matches):
        code = normalize_step_code(match.group(1))
        if not code:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = normalize_display_text(text[match.start():end])
        if not segment:
            continue
        split_item = {**item}
        split_item["text"] = segment
        split_item["content"] = segment
        split_item["title"] = segment
        split_item["step_code"] = code
        if original_id:
            split_item["id"] = f"{original_id}_step_{code.replace('.', '_')}"
        metadata = split_item.get("metadata") if isinstance(split_item.get("metadata"), dict) else {}
        split_item["metadata"] = {
            **metadata,
            "split_from_node_id": original_id,
            "split_step_code": code,
        }
        output.append(split_item)
    return output or [item]


def compile_canvas_annotations(filename: str, canvas: dict[str, Any], node_lookup: dict[str, str]) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for page in canvas.get("pages", []):
        candidates = [*page.get("annotations", [])]
        for node in page.get("nodes", []):
            if isinstance(node, dict) and is_note_text(node_text(node)):
                candidates.append(node)
        for index, item in enumerate(candidates, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("content") or item.get("title") or item.get("note") or "").strip()
            if not text:
                continue
            page_number = int_or_default(item.get("page"), page.get("page") or 1)
            attached_codes = metadata_list(item.get("attached_to_step_codes") or item.get("attached_to") or item.get("attached_to_node_ids"))
            attached_ids = [node_lookup.get(str(code), str(code)) for code in attached_codes if str(code)]
            attached_ids = enrich_annotation_attachment_ids(text, attached_ids, node_lookup)
            annotation_type = infer_annotation_type(item, text)
            annotation_id = stable_node_id(item.get("id") or text, prefix="ann")
            annotations.append(
                {
                    "id": annotation_id,
                    "type": annotation_type,
                    "attached_to": attached_ids[0] if attached_ids else "",
                    "attached_to_node_ids": attached_ids,
                    "title": annotation_title(text, annotation_type),
                    "content": text,
                    "risk_level": "high" if annotation_type in {"warning", "audit_rule"} else "",
                    "source_refs": [source_ref(filename, page_number, item.get("bbox"))],
                    "bbox": normalize_bbox(item.get("bbox")),
                    "page": page_number,
                }
            )
    return dedupe_annotations(annotations)


def sanitize_canvas_node_metadata(metadata: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(metadata, dict):
        return {}, []
    sanitized: dict[str, Any] = {}
    repairs: list[str] = []
    for key, value in metadata.items():
        key_text = normalized_text(str(key))
        value_text = normalized_text(str(value)) if isinstance(value, (str, int, float, bool)) else ""
        if key_text in {"not_decision", "is_decision"} or "not decision" in value_text or "not a decision" in value_text:
            repairs.append(f"invalid_review_metadata_removed:{key}")
            continue
        sanitized[key] = value
    return sanitized, repairs


def attach_orphan_annotations_to_nearest_node(annotations: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> list[str]:
    repairs: list[str] = []
    workflow_nodes = [node for node in nodes if node.get("type") not in {"start", "end"}]
    for annotation in annotations:
        attached = [str(item) for item in annotation.get("attached_to_node_ids", []) if str(item)]
        if attached:
            continue
        nearest_id = nearest_node_id_by_bbox(annotation.get("bbox"), workflow_nodes)
        if nearest_id:
            annotation["attached_to"] = nearest_id
            annotation["attached_to_node_ids"] = [nearest_id]
            repairs.append(f"orphan_annotation_attached:{annotation.get('id')}->{nearest_id}")
        else:
            annotation["orphan_annotation"] = True
            repairs.append(f"orphan_annotation_flagged:{annotation.get('id')}")
    return repairs


def nearest_node_id_by_bbox(annotation_bbox: Any, nodes: list[dict[str, Any]]) -> str:
    bbox = normalize_bbox(annotation_bbox)
    if len(bbox) < 4:
        return ""
    best_id = ""
    best_distance = float("inf")
    for node in nodes:
        node_bbox = normalize_bbox(node.get("bbox"))
        if len(node_bbox) < 4:
            continue
        distance = bbox_center_distance(bbox, node_bbox)
        if distance < best_distance:
            best_distance = distance
            best_id = str(node.get("id") or "")
    return best_id


def bbox_center_distance(a: list[float], b: list[float]) -> float:
    ax = (a[0] + a[2]) / 2
    ay = (a[1] + a[3]) / 2
    bx = (b[0] + b[2]) / 2
    by = (b[1] + b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def compile_canvas_relations(filename: str, canvas: dict[str, Any]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for page in canvas.get("pages", []):
        note_nodes = [node for node in page.get("nodes", []) if isinstance(node, dict) and is_note_text(node_text(node))]
        candidates = [*page.get("relations", []), *page.get("annotations", []), *note_nodes]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            text = str(item.get("evidence_text") or item.get("text") or item.get("content") or item.get("title") or "").strip()
            target_title = str(item.get("target_title") or relation_target_from_text(text)).strip()
            if not target_title:
                continue
            page_number = int_or_default(item.get("page"), page.get("page") or 1)
            relations.append(
                {
                    "target_title": target_title[:300],
                    "target_url": str(item.get("target_url") or item.get("url") or ""),
                    "relation_type": normalize_relation_type(item.get("relation_type") or "requires", text),
                    "relation_source": str(item.get("relation_source") or "explicit_text_reference"),
                    "evidence_text": text[:500],
                    "attached_to_step_codes": [
                        normalize_step_code(code)
                        for code in list_payload(item.get("attached_to_step_codes") or item.get("attached_steps") or item.get("steps"))
                        if normalize_step_code(code)
                    ],
                    "confidence": clamp_float(item.get("confidence"), 0.4, 0.95, 0.82),
                    "source_refs": [source_ref(filename, page_number, item.get("bbox"))],
                }
            )
    return dedupe_relations(relations)


def compile_canvas_edges(
    filename: str,
    canvas: dict[str, Any],
    node_lookup: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], set[tuple[str, str, str]]]:
    edges: list[dict[str, Any]] = []
    uncertain_edges: list[dict[str, Any]] = []
    conflicts: list[str] = []
    expected_edges: set[tuple[str, str, str]] = set()
    seen: set[tuple[str, str, str]] = set()
    for page in canvas.get("pages", []):
        for item in page.get("edges", []):
            if not isinstance(item, dict):
                continue
            from_key = str(item.get("from_step_code") or item.get("from_node") or item.get("from") or item.get("source") or "")
            to_key = str(item.get("to_step_code") or item.get("to_node") or item.get("to") or item.get("target") or "")
            from_node = resolve_edge_endpoint(from_key, node_lookup, role="from")
            to_node = resolve_edge_endpoint(to_key, node_lookup, role="to")
            condition = normalize_condition(item.get("condition") or item.get("label") or "")
            confidence = clamp_float(item.get("confidence"), 0.0, 1.0, 0.72)
            page_number = int_or_default(item.get("page"), page.get("page") or 1)
            if from_node and to_node:
                expected_edges.add((from_node, to_node, condition))
            edge_payload = {
                "from_node": from_node,
                "to_node": to_node,
                "condition": condition,
                "confidence": confidence,
                "review_status": str(item.get("review_status") or "needs_review"),
                "review_reason": str(item.get("reason") or item.get("review_reason") or ""),
                "source_refs": [source_ref(filename, page_number, item.get("bbox"))],
            }
            if not from_node or not to_node:
                conflicts.append(f"edge_endpoint_not_resolved:{from_key}->{to_key}")
                uncertain_edges.append(
                    {
                        **edge_payload,
                        "reason": f"Không resolve được endpoint edge từ canvas: {from_key}->{to_key}",
                        "confidence": min(confidence, 0.35),
                    }
                )
                continue
            key = (from_node, to_node, condition)
            if key in seen:
                conflicts.append(f"duplicate_edge_merged:{from_node}->{to_node}:{condition}")
                continue
            seen.add(key)
            if bool(item.get("uncertain")):
                uncertain_edges.append({**edge_payload, "reason": str(item.get("reason") or "AI marked this connector uncertain.")})
            else:
                edges.append(edge_payload)
    return edges, uncertain_edges, conflicts, expected_edges


def ensure_boundary_nodes(
    filename: str,
    raw_text: str,
    title_hint: str,
    canvas: dict[str, Any],
    nodes: list[dict[str, Any]],
    node_lookup: dict[str, str],
) -> list[str]:
    if not nodes:
        return []
    conflicts: list[str] = []
    if not any(node.get("type") == "start" for node in nodes):
        source_hint = f"{raw_text}\n{title_hint}"
        raw_norm = normalized_text(source_hint)
        start = {
            "id": "start",
            "type": "start",
            "semantic_node_type": "start",
            "step_code": "",
            "shape_kind": "synthetic",
            "actor": "KH/TX" if "kh tx" in raw_norm or "hotro be" in raw_norm or "ho tro be" in raw_norm else "",
            "lane_id": "lane_customer_driver" if "hotro be" in raw_norm or "ho tro be" in raw_norm else "",
            "phase": "",
            "title": synthesized_start_title(source_hint),
            "content": synthesized_start_title(source_hint),
            "question": "",
            "terminal_state": "",
            "metadata": {"synthesized": True, "reason": "missing_start_node"},
            "source_refs": [page_source_ref(filename, canvas)],
            "bbox": [],
            "page": int_or_default(next((page.get("page") for page in canvas.get("pages", []) if isinstance(page, dict)), 1), 1),
            "attached_annotations": [],
            "dedupe_status": "synthesized",
        }
        nodes.insert(0, start)
        node_lookup["start"] = "start"
        conflicts.append("workflow_v3_start_node_synthesized")
    if not any(node.get("type") == "end" for node in nodes):
        end = {
            "id": "end",
            "type": "end",
            "semantic_node_type": "end",
            "step_code": "",
            "shape_kind": "synthetic",
            "actor": "",
            "lane_id": "",
            "phase": "",
            "title": "End",
            "content": "End",
            "question": "",
            "terminal_state": "terminal",
            "metadata": {"synthesized": True, "reason": "missing_end_node"},
            "source_refs": [page_source_ref(filename, canvas)],
            "bbox": [],
            "page": int_or_default(next((page.get("page") for page in canvas.get("pages", []) if isinstance(page, dict)), 1), 1),
            "attached_annotations": [],
            "dedupe_status": "synthesized",
        }
        nodes.append(end)
        node_lookup["end"] = "end"
        conflicts.append("workflow_v3_end_node_synthesized")
    for node in nodes:
        node_lookup[str(node.get("id"))] = str(node.get("id"))
    add_boundary_aliases(node_lookup, nodes)
    return conflicts


def ensure_boundary_and_terminal_edges(
    filename: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    uncertain_edges: list[dict[str, Any]],
) -> list[str]:
    conflicts: list[str] = []
    node_by_id = {str(node.get("id")): node for node in nodes}
    start_id = first_start_node_id(nodes)
    end_id = next((str(node.get("id")) for node in nodes if node.get("type") == "end"), "")
    edge_keys = {(str(edge.get("from_node")), str(edge.get("to_node")), normalize_condition(edge.get("condition"))) for edge in [*edges, *uncertain_edges]}

    if start_id and not has_resolved_outgoing_edge(start_id, edges, uncertain_edges):
        first_target = first_root_node_id(nodes, edges, uncertain_edges, start_id)
        if first_target and (start_id, first_target, "next") not in edge_keys:
            edges.append(synthetic_edge(filename, node_by_id[start_id], node_by_id[first_target], "next", "synthesized_start_edge"))
            edge_keys.add((start_id, first_target, "next"))
            conflicts.append(f"workflow_v3_start_edge_synthesized:{start_id}->{first_target}")

    if not end_id:
        return conflicts
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node.get("type") in {"start", "end", "decision"}:
            continue
        if has_resolved_outgoing_edge(node_id, edges, uncertain_edges):
            continue
        if is_external_continuation_node(node):
            continue
        if not terminal_action_evidence(node):
            continue
        if (node_id, end_id, "next") in edge_keys:
            continue
        edges.append(synthetic_edge(filename, node, node_by_id[end_id], "next", "synthesized_terminal_edge"))
        edge_keys.add((node_id, end_id, "next"))
        conflicts.append(f"workflow_v3_terminal_edge_synthesized:{node.get('step_code') or node_id}->{end_id}")
    return conflicts


def first_root_node_id(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    uncertain_edges: list[dict[str, Any]],
    start_id: str,
) -> str:
    incoming = {str(edge.get("to_node")) for edge in [*edges, *uncertain_edges] if edge.get("to_node")}
    candidates = [
        node for node in nodes
        if node.get("type") not in {"start", "end"} and str(node.get("id")) not in incoming
    ]
    if not candidates:
        candidates = [node for node in nodes if node.get("type") not in {"start", "end"}]
    if not candidates:
        return ""
    candidates.sort(key=lambda node: (0 if node.get("type") == "decision" else 1, step_sort_key(str(node.get("step_code") or "999")), str(node.get("id"))))
    target = str(candidates[0].get("id") or "")
    return "" if target == start_id else target


def has_resolved_outgoing_edge(node_id: str, edges: list[dict[str, Any]], uncertain_edges: list[dict[str, Any]]) -> bool:
    return any(
        str(edge.get("from_node") or "") == node_id and bool(edge.get("to_node"))
        for edge in [*edges, *uncertain_edges]
    )


def synthetic_edge(filename: str, from_node: dict[str, Any], to_node: dict[str, Any], condition: str, reason: str) -> dict[str, Any]:
    refs = from_node.get("source_refs") if isinstance(from_node.get("source_refs"), list) else []
    if not refs:
        refs = to_node.get("source_refs") if isinstance(to_node.get("source_refs"), list) else []
    if not refs:
        refs = [source_ref(filename, int_or_default(from_node.get("page") or to_node.get("page"), 1), [])]
    return {
        "from_node": str(from_node.get("id") or ""),
        "to_node": str(to_node.get("id") or ""),
        "condition": normalize_condition(condition),
        "confidence": 0.72,
        "review_status": "needs_review",
        "review_reason": reason,
        "source_refs": refs[:2],
    }


def workflow_v3_fidelity_report(
    *,
    nodes: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    uncertain_edges: list[dict[str, Any]],
    visible_step_codes: list[str],
    expected_edges: set[tuple[str, str, str]],
    detector_conflicts: list[str],
) -> dict[str, Any]:
    node_codes = {str(node.get("step_code") or "") for node in nodes if node.get("step_code")}
    annotation_codes = {extract_step_code(annotation.get("content", "")) for annotation in annotations}
    covered_step_codes = sorted(code for code in (node_codes | annotation_codes) if code)
    missing_step_codes = [code for code in visible_step_codes if code not in set(covered_step_codes)]
    edge_keys = {(str(edge.get("from_node")), str(edge.get("to_node")), normalize_condition(edge.get("condition"))) for edge in [*edges, *uncertain_edges]}
    missing_expected_edges = sorted(f"{from_node}->{to_node}:{condition}" for from_node, to_node, condition in expected_edges if (from_node, to_node, condition) not in edge_keys)
    blockers: list[str] = []
    warnings: list[str] = []

    if visible_step_codes and missing_step_codes:
        blockers.append(f"workflow_v3_missing_visible_steps:{','.join(missing_step_codes[:12])}")
    if len(visible_step_codes) >= 4 and len(nodes) < max(3, int(len(visible_step_codes) * 0.55)):
        blockers.append("workflow_v3_summary_like_graph_too_few_nodes")
    if missing_expected_edges:
        blockers.append(f"workflow_v3_missing_visible_edges:{';'.join(missing_expected_edges[:8])}")
    node_ids = [str(node.get("id") or "") for node in nodes]
    duplicate_ids = sorted({node_id for node_id in node_ids if node_id and node_ids.count(node_id) > 1})
    if duplicate_ids:
        blockers.append(f"workflow_v3_duplicate_node_ids:{','.join(duplicate_ids[:8])}")
    node_by_id = {node["id"]: node for node in nodes}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    uncertain_outgoing: dict[str, list[dict[str, Any]]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    uncertain_incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        outgoing.setdefault(str(edge.get("from_node")), []).append(edge)
        incoming.setdefault(str(edge.get("to_node")), []).append(edge)
    for edge in uncertain_edges:
        if edge.get("from_node") and edge.get("to_node"):
            uncertain_outgoing.setdefault(str(edge.get("from_node")), []).append(edge)
            uncertain_incoming.setdefault(str(edge.get("to_node")), []).append(edge)
    for node in nodes:
        node_id = str(node.get("id") or "")
        text = " ".join(str(node.get(key) or "") for key in ("title", "question", "content"))
        branch_conditions = [
            normalize_condition(edge.get("condition"))
            for edge in [*outgoing.get(node_id, []), *uncertain_outgoing.get(node_id, [])]
        ]
        if node.get("type") not in {"decision", "start", "end"} and {"yes", "no"}.issubset(set(branch_conditions)):
            blockers.append(f"workflow_v3_branching_node_not_decision:{node.get('step_code') or node_id}")
        if node.get("type") == "decision":
            if decision_metadata_says_not_decision(node.get("metadata")):
                blockers.append(f"workflow_v3_decision_marked_not_decision:{node.get('step_code') or node_id}")
            conditions = branch_conditions
            if len(conditions) < 2:
                blockers.append(f"workflow_v3_decision_missing_two_branches:{node.get('step_code') or node_id}")
            elif not (any(condition == "yes" for condition in conditions) and any(condition == "no" for condition in conditions)):
                blockers.append(f"workflow_v3_decision_missing_yes_no:{node.get('step_code') or node_id}")
        if node.get("type") == "end" and (outgoing.get(node_id) or uncertain_outgoing.get(node_id)):
            blockers.append(f"workflow_v3_end_has_outgoing:{node_id}")
        if node.get("type") == "start" and (incoming.get(node_id) or uncertain_incoming.get(node_id)):
            blockers.append(f"workflow_v3_start_has_incoming:{node_id}")
        if node.get("type") not in {"decision", "start", "end"}:
            has_outgoing = bool(outgoing.get(node_id) or uncertain_outgoing.get(node_id))
            if not has_outgoing and not is_external_continuation_node(node):
                blockers.append(f"workflow_v3_action_missing_terminal_or_outgoing:{node.get('step_code') or node_id}")
    for edge in edges:
        if edge.get("from_node") not in node_by_id or edge.get("to_node") not in node_by_id:
            blockers.append(f"workflow_v3_edge_unknown_endpoint:{edge.get('from_node')}->{edge.get('to_node')}")
        if normalize_condition(edge.get("condition")) not in VALID_EDGE_CONDITIONS:
            blockers.append(f"workflow_v3_invalid_edge_condition:{edge.get('condition')}")
    if uncertain_edges:
        warnings.append(f"workflow_v3_uncertain_edges_require_review:{len(uncertain_edges)}")
    warnings.extend(detector_conflicts[:12])

    coverage = 1.0
    if visible_step_codes:
        coverage = max(0.0, 1.0 - (len(missing_step_codes) / max(len(visible_step_codes), 1)))
    edge_coverage = 1.0
    if expected_edges:
        edge_coverage = max(0.0, 1.0 - (len(missing_expected_edges) / max(len(expected_edges), 1)))
    fidelity_score = max(0.2, min(0.95, 0.35 + coverage * 0.35 + edge_coverage * 0.2 - min(len(blockers) * 0.06, 0.28)))
    return {
        "strategy": "workflow_v3_graph_primary",
        "visible_step_codes": visible_step_codes,
        "covered_step_codes": covered_step_codes,
        "missing_step_codes": missing_step_codes,
        "expected_edge_count": len(expected_edges),
        "missing_expected_edges": missing_expected_edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "uncertain_edge_count": len(uncertain_edges),
        "detector_conflicts": list(dict.fromkeys(detector_conflicts)),
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "fidelity_score": round(fidelity_score, 3),
    }


def workflow_graph_repair_report(
    *,
    nodes: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    uncertain_edges: list[dict[str, Any]],
    repair_events: list[str],
    fidelity_report: dict[str, Any],
) -> dict[str, Any]:
    node_ids = {str(node.get("id") or "") for node in nodes}
    edge_pairs = [(str(edge.get("from_node") or ""), str(edge.get("to_node") or "")) for edge in [*edges, *uncertain_edges]]
    outgoing = {from_node for from_node, to_node in edge_pairs if from_node and to_node}
    decision_edges_review_required = sum(
        1
        for edge in edges
        if normalize_condition(edge.get("condition")) in {"yes", "no"}
        and str(edge.get("review_status") or "") not in {"confirmed", "acknowledged"}
    )
    missing_terminal_edges = [
        str(node.get("step_code") or node.get("id") or "")
        for node in nodes
        if node.get("type") not in {"start", "end", "decision"}
        and str(node.get("id") or "") not in outgoing
        and not is_external_continuation_node(node)
    ]
    orphan_annotations = [
        str(annotation.get("id") or annotation.get("title") or "")
        for annotation in annotations
        if not annotation.get("attached_to_node_ids")
    ]
    unresolved_relations = [
        {
            "target_title": relation.get("target_title"),
            "target_url": relation.get("target_url"),
            "relation_type": relation.get("relation_type"),
            "evidence_text": relation.get("evidence_text"),
        }
        for relation in relations
        if relation.get("target_title") and not relation.get("target_id")
    ]
    source_ref_missing = [
        str(node.get("step_code") or node.get("id") or "")
        for node in nodes
        if not node.get("source_refs")
    ]
    invalid_edge_endpoints = [
        f"{from_node}->{to_node}"
        for from_node, to_node in edge_pairs
        if from_node not in node_ids or to_node not in node_ids
    ]
    repairable_events = [
        event
        for event in repair_events
        if event.startswith(
            (
                "workflow_v3_start_node_synthesized",
                "workflow_v3_end_node_synthesized",
                "workflow_v3_start_edge_synthesized",
                "workflow_v3_terminal_edge_synthesized",
                "duplicate_node_merged",
                "duplicate_node_id_renamed",
                "duplicate_edge_merged",
                "orphan_annotation_attached",
                "invalid_review_metadata_removed",
            )
        )
    ]
    return {
        "stage": "workflow_graph_repair",
        "repair_applied": bool(repairable_events),
        "repair_events": list(dict.fromkeys(repairable_events)),
        "unrepairable_events": [
            event
            for event in repair_events
            if event not in set(repairable_events)
        ][:20],
        "graph_fidelity_score": fidelity_report.get("fidelity_score"),
        "decision_edges_review_required": decision_edges_review_required,
        "missing_terminal_edges": missing_terminal_edges,
        "orphan_annotations": orphan_annotations,
        "unresolved_relations": unresolved_relations,
        "source_ref_missing_nodes": source_ref_missing,
        "invalid_edge_endpoints": invalid_edge_endpoints,
        "blockers_after_repair": fidelity_report.get("blockers", []),
        "warnings_after_repair": fidelity_report.get("warnings", []),
    }


def workflow_v3_quality_error_from_report(report: dict[str, Any]) -> str:
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        return ",".join(str(blocker) for blocker in blockers[:6])
    if float(report.get("fidelity_score") or 0) < 0.68:
        return "workflow_v3_low_fidelity_score"
    return ""


def visible_step_codes_from_sources(raw_text: str, canvas: dict[str, Any], visual_context: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for page in canvas.get("pages", []):
        for node in page.get("nodes", []):
            if isinstance(node, dict):
                code = normalize_step_code(node.get("step_code") or extract_step_code(node_text(node)))
                if code:
                    codes.append(code)
    for page in visual_context.get("pages", []) if isinstance(visual_context.get("pages"), list) else []:
        for node in page.get("nodes", []):
            if isinstance(node, dict):
                text = str(node.get("title") or node.get("text") or "")
                if is_note_text(text):
                    continue
                code = extract_step_code(text)
                if code:
                    codes.append(code)
    codes.extend(raw_text_visible_step_codes(raw_text))
    return sorted(dict.fromkeys(codes), key=step_sort_key)


def raw_text_visible_step_codes(raw_text: str) -> list[str]:
    codes: list[str] = []
    for line in raw_text.splitlines():
        code = extract_step_code_from_line(line)
        if code and is_workflow_like_step_line(line):
            codes.append(code)
    return codes


def is_workflow_like_step_line(line: str) -> bool:
    stripped = normalize_display_text(line)
    if not stripped or is_note_text(stripped):
        return False
    if len(stripped) > 420:
        return False
    lower = normalized_text(stripped)
    if lower.startswith(("vd ", "vi du ", "example ", "no ", "ten hang ", "sdt ")):
        return False
    return bool(WORKFLOW_LINE_HINT_RE.search(stripped))


def workflow_v3_full_sop_content(graph: dict[str, Any], annotations: list[dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    lines = [f"Workflow graph: {graph.get('title')}", "", "Nodes:"]
    for node in graph.get("nodes", []):
        label = node.get("question") or node.get("content") or node.get("title")
        prefix = f"{node.get('step_code')}. " if node.get("step_code") else ""
        lines.append(f"- {prefix}{label}")
    lines.extend(["", "Edges:"])
    for edge in graph.get("edges", []):
        lines.append(f"- {edge.get('from_node')} --{edge.get('condition')}--> {edge.get('to_node')}")
    if annotations:
        lines.extend(["", "Annotations:"])
        lines.extend(f"- {annotation.get('title')}: {annotation.get('content')}" for annotation in annotations)
    if relations:
        lines.extend(["", "Relations:"])
        lines.extend(f"- {relation.get('relation_type')}: {relation.get('target_title')}" for relation in relations)
    return "\n".join(lines).strip()


def workflow_v3_atomic_units(
    graph: dict[str, Any],
    annotations: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    confidence: float,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if node.get("type") in {"start", "end"}:
            continue
        unit_type = atomic_unit_type_for_node(node)
        content = str(node.get("question") or node.get("content") or node.get("title") or "").strip()
        if not content:
            continue
        units.append(
            {
                "unit_type": unit_type,
                "title": str(node.get("title") or content)[:180],
                "content": content,
                "confidence": confidence,
                "metadata": {
                    "retrieval_scope": "unit",
                    "workflow_v3": True,
                    "workflow_node_id": node.get("id"),
                    "step_code": node.get("step_code"),
                    "actor": node.get("actor"),
                    "shape_kind": node.get("shape_kind"),
                    "terminal_state": node.get("terminal_state"),
                    "source_refs": node.get("source_refs", []),
                },
                "source_refs": node.get("source_refs", []),
            }
        )
    for annotation in annotations:
        unit_type = "warning" if annotation.get("type") in {"warning", "audit_rule"} else "operational_note"
        units.append(
            {
                "unit_type": unit_type,
                "title": annotation.get("title") or "Lưu ý workflow",
                "content": annotation.get("content") or "",
                "confidence": min(confidence, 0.78),
                "metadata": {
                    "retrieval_scope": "annotation",
                    "workflow_v3": True,
                    "annotation_id": annotation.get("id"),
                    "attached_to": annotation.get("attached_to"),
                    "attached_to_node_ids": annotation.get("attached_to_node_ids", []),
                    "source_refs": annotation.get("source_refs", []),
                },
                "source_refs": annotation.get("source_refs", []),
            }
        )
    for relation in relations:
        units.append(
            {
                "unit_type": "related_document",
                "title": relation.get("target_title") or "Tài liệu liên quan",
                "content": relation.get("evidence_text") or f"Tài liệu liên quan: {relation.get('target_title')}",
                "confidence": min(float(relation.get("confidence") or confidence), 0.9),
                "metadata": {
                    "retrieval_scope": "relation",
                    "workflow_v3": True,
                    "target_title": relation.get("target_title"),
                    "target_url": relation.get("target_url"),
                    "relation_type": relation.get("relation_type") or "requires",
                    "relations": [relation],
                    "source_refs": relation.get("source_refs", []),
                },
                "source_refs": relation.get("source_refs", []),
            }
        )
    return units[:100]


def atomic_unit_type_for_node(node: dict[str, Any]) -> str:
    text = normalized_text(" ".join(str(node.get(key) or "") for key in ("semantic_node_type", "title", "question", "content")))
    if node.get("type") == "decision":
        return "decision_point"
    if "sla" in text or re.search(r"\b\d+\s*(phút|phut|giờ|gio)\b", text):
        return "sla_rule"
    if "queue" in text or "chuyển case" in text or "chuyen case" in text:
        return "routing_rule"
    if "gọi ra" in text or "call in app" in text or "liên hệ" in text:
        return "handoff_rule"
    return "workflow_step"


def workflow_v3_review_reason(report: dict[str, Any]) -> str:
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        return "Workflow V3 extracted a graph but fidelity blockers require manual review before publish."
    if report.get("uncertain_edge_count"):
        return "Workflow V3 extracted uncertain edges that require manual branch review."
    return "Workflow V3 graph extracted from page image and still requires human topology review."


def synthesized_start_title(raw_text: str) -> str:
    normalized = normalized_text(raw_text)
    if "hotro be com vn" in normalized or "hotro be" in normalized:
        return "KH/TX liên hệ qua email hotro@be.com.vn"
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw_text or "")
    if email_match:
        email = email_match.group(0)
        if normalized_text(email) == "ho tro be com vn":
            email = "hotro@be.com.vn"
        return f"KH/TX liên hệ qua email {email}"
    return "Start"


def first_start_node_id(nodes: list[dict[str, Any]]) -> str:
    return next((node["id"] for node in nodes if node.get("type") == "start"), nodes[0]["id"] if nodes else "start")


def workflow_lanes(nodes: list[dict[str, Any]], canvas: dict[str, Any]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for page in canvas.get("pages", []):
        for lane in page.get("lanes", []):
            if isinstance(lane, dict):
                name = str(lane.get("title") or lane.get("name") or lane.get("actor") or lane.get("id") or "").strip()
                if name:
                    lanes.append({"id": normalized_key(name) or stable_node_id(name, "lane"), "actor": name, "bbox": normalize_bbox(lane.get("bbox"))})
    seen = {lane["actor"] for lane in lanes}
    for actor in dict.fromkeys(str(node.get("actor") or "") for node in nodes if node.get("actor")):
        if actor not in seen:
            lanes.append({"id": normalized_key(actor) or stable_node_id(actor, "lane"), "actor": actor, "node_ids": [node["id"] for node in nodes if node.get("actor") == actor]})
    return lanes


def infer_node_type(item: dict[str, Any], text: str, step_code: str) -> str:
    raw_type = normalized_text(str(item.get("node_type") or item.get("type") or item.get("semantic_node_type") or ""))
    shape = normalized_text(str(item.get("shape_kind") or item.get("shape") or ""))
    clean = normalized_text(text)
    if raw_type == "end" or clean in {"end", "ket thuc"}:
        return "end"
    if raw_type == "start" and not step_code:
        return "start"
    if "diamond" in shape or "rhombus" in shape or "decision" in raw_type:
        return "decision"
    if "?" in text and raw_type not in {"action", "task", "process", "step"} and "rectangle" not in shape:
        return "decision"
    if "oval" in shape and not step_code:
        return "start"
    return "action"


def node_identifier(item: dict[str, Any], node_type: str, step_code: str, text: str) -> str:
    if step_code:
        return stable_node_id(step_code, prefix="node")
    if node_type == "start":
        return "start"
    if node_type == "end":
        return "end"
    return stable_node_id(item.get("id") or text, prefix="node")


def ensure_unique_node_ids(nodes: list[dict[str, Any]], conflicts: list[str]) -> None:
    seen: dict[str, int] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id not in seen:
            seen[node_id] = 1
            continue
        seen[node_id] += 1
        new_id = f"{node_id}_{seen[node_id]}"
        conflicts.append(f"duplicate_node_id_renamed:{node_id}->{new_id}")
        node["id"] = new_id


def add_lookup_alias(lookup: dict[str, str], alias: Any, node_id: str) -> bool:
    key = str(alias or "").strip()
    if not key:
        return True
    existing = lookup.get(key)
    if existing and existing != node_id:
        return False
    lookup[key] = node_id
    return True


def add_boundary_aliases(lookup: dict[str, str], nodes: list[dict[str, Any]]) -> None:
    start = next((str(node.get("id")) for node in nodes if node.get("type") == "start"), "")
    end = next((str(node.get("id")) for node in nodes if node.get("type") == "end"), "")
    if start:
        for alias in ("start", "START", "Start", "begin", "BEGIN", "bat_dau"):
            add_lookup_alias(lookup, alias, start)
    if end:
        for alias in ("end", "END", "End", "finish", "FINISH", "done", "DONE", "ket_thuc"):
            add_lookup_alias(lookup, alias, end)


def resolve_edge_endpoint(raw_key: Any, node_lookup: dict[str, str], role: str) -> str:
    key = str(raw_key or "").strip()
    if not key:
        return ""
    boundary_alias = boundary_edge_alias(key, role)
    if boundary_alias and node_lookup.get(boundary_alias):
        return node_lookup[boundary_alias]
    code = normalize_step_code(key)
    if code and node_lookup.get(code):
        return node_lookup[code]
    return node_lookup.get(key, node_lookup.get(normalized_key(key), ""))


def boundary_edge_alias(key: str, role: str) -> str:
    normalized = normalized_key(key)
    if normalized in {"start", "begin", "bat_dau"}:
        return "start"
    if normalized in {"end", "finish", "done", "ket_thuc"}:
        return "end"
    if normalized == "0":
        return ""
    if role == "from" and normalized in {"source_start", "workflow_start"}:
        return "start"
    if role == "to" and normalized in {"target_end", "workflow_end"}:
        return "end"
    return ""


def is_ambiguous_boundary_source_id(source_id: Any) -> bool:
    return normalized_key(str(source_id or "")) in {"0"}


def node_title(text: str, step_code: str, node_type: str) -> str:
    if node_type == "decision":
        return decision_question(text)[:240]
    cleaned = normalize_display_text(text)
    if step_code and cleaned.startswith(step_code):
        return cleaned[:180]
    return cleaned[:180]


def decision_question(text: str) -> str:
    cleaned = re.sub(r"^\s*(?:yes|no|có|không)\s+", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(?:bước\s*)?\d{1,2}(?:\.\d{1,2})?[.)]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = normalize_display_text(cleaned)
    return cleaned if cleaned.endswith("?") else f"{cleaned}?"


def terminal_state_for_text(text: str) -> str:
    normalized = normalized_text(text)
    if "status resolved" in normalized or "resolve case" in normalized:
        return "resolved"
    if "chua the ho tro" in normalized or "khong thanh cong" in normalized:
        return "closed_with_response"
    if "xu ly theo quy trinh" in normalized or "tiep tuc ho tro" in normalized:
        return "continue_to_related_process"
    return ""


def normalize_terminal_state(value: Any) -> str:
    normalized = normalized_key(str(value or ""))
    if normalized in {"", "none", "null"}:
        return ""
    if normalized in {"continues_with_related_sop", "continue_with_related_sop"}:
        return "continues_with_related_sop"
    return normalized


def terminal_action_evidence(node: dict[str, Any]) -> bool:
    if node.get("terminal_state"):
        return True
    text = normalized_text(" ".join(str(node.get(key) or "") for key in ("title", "content")))
    terminal_phrases = [
        "status resolved",
        "resolve case",
        "resolved",
        "phan hoi email",
        "phan hoi mail",
        "gui mail",
        "gui email",
        "chua the ho tro",
        "khong thanh cong",
        "cung cap thong tin theo quy dinh",
        "xu ly theo quy trinh",
        "xu ly theo quy dinh",
        "tiep tuc ho tro",
        "lien he khai thac them thong tin",
    ]
    return any(phrase in text for phrase in terminal_phrases)


def is_external_continuation_node(node: dict[str, Any]) -> bool:
    terminal_state = normalize_terminal_state(node.get("terminal_state"))
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    return terminal_state in EXTERNAL_CONTINUATION_STATES or bool(metadata.get("continues_with_related_sop"))


def decision_metadata_says_not_decision(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("is_decision") is False or metadata.get("not_decision") is True:
        return True
    text = normalized_text(" ".join(str(metadata.get(key) or "") for key in ("review_status", "decision_status", "classification", "note")))
    return "not decision" in text or "not a decision" in text


def infer_annotation_type(item: dict[str, Any], text: str) -> str:
    raw_type = normalized_text(str(item.get("annotation_type") or item.get("type") or item.get("unit_type") or ""))
    normalized = normalized_text(text)
    if "audit" in raw_type or "audit" in normalized or "zt" in normalized:
        return "audit_rule"
    if "warning" in raw_type or "canh bao" in normalized:
        return "warning"
    if "sla" in raw_type or "sla" in normalized:
        return "sla_rule"
    if "script" in raw_type or "macro" in raw_type:
        return "macro_script"
    return "annotation"


def enrich_annotation_attachment_ids(text: str, attached_ids: list[str], node_lookup: dict[str, str]) -> list[str]:
    normalized = normalized_text(text)
    preferred: list[str] = []
    if "thong tin chung" in normalized and node_lookup.get("1"):
        preferred.append(node_lookup["1"])
    if "case si" in normalized and node_lookup.get("6.1"):
        preferred.append(node_lookup["6.1"])
    output: list[str] = []
    for node_id in [*preferred, *attached_ids]:
        if node_id and node_id not in output:
            output.append(node_id)
    return output


def annotation_title(text: str, annotation_type: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:180] or annotation_type.replace("_", " ").title()


def relation_target_from_text(text: str) -> str:
    patterns = [
        r"(Quy định\s+[^\n]+?\.xlsx)",
        r"(Quy trình\s+[^\n]+?\.xlsx)",
        r"(Quy định\s+[^\n]+)",
        r"(Quy trình\s+[^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_display_text(match.group(1)).strip(" .:")
    return ""


def normalize_relation_type(value: Any, text: str) -> str:
    normalized = normalized_text(str(value or ""))
    if normalized in {"requires", "must_follow", "references", "related_to", "routes_to", "escalates_to", "exception_of", "supersedes"}:
        return normalized
    text_norm = normalized_text(text)
    if "theo quy dinh" in text_norm or "theo quy trinh" in text_norm or "luu y chung" in text_norm:
        return "requires"
    return "references"


def is_note_text(text: str) -> bool:
    return bool(NOTE_MARKER_RE.search(text.strip()))


def extract_step_code(text: str) -> str:
    cleaned = re.sub(r"^\s*(?:yes|no|có|không)\s+", "", str(text or "").strip(), flags=re.IGNORECASE)
    match = STEP_CODE_RE.search(cleaned)
    return normalize_step_code(match.group(1)) if match else ""


def extract_step_code_from_line(line: str) -> str:
    if is_note_text(line):
        return ""
    match = LINE_STEP_CODE_RE.search(line)
    return normalize_step_code(match.group(1)) if match else ""


def normalize_step_code(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"\d{1,2}(?:\.\d{1,2})?", text)
    return match.group(0).strip(".") if match else ""


def step_sort_key(code: str) -> tuple[int, ...]:
    return tuple(int(part) for part in str(code).split(".") if part.isdigit())


def stable_node_id(value: Any, prefix: str = "node") -> str:
    base = normalize_step_code(value)
    if base:
        return f"{prefix}_{base.replace('.', '_')}"
    key = normalized_key(str(value or ""))[:80] or "item"
    return f"{prefix}_{key}"


def source_ref(filename: str, page: int, bbox: Any) -> dict[str, Any]:
    return {"source_type": "pdf_diagram", "source_file": filename, "page": int_or_default(page, 1), "bbox": normalize_bbox(bbox)}


def page_source_ref(filename: str, canvas: dict[str, Any]) -> dict[str, Any]:
    first = next((page for page in canvas.get("pages", []) if isinstance(page, dict)), {})
    image_size = first.get("image_size") if isinstance(first.get("image_size"), list) else []
    bbox: list[float] = []
    if len(image_size) >= 2:
        bbox = [0.0, 0.0, float_or_default(image_size[0]), float_or_default(image_size[1])]
    return source_ref(filename, int_or_default(first.get("page"), 1), bbox)


def normalize_bbox(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) < 4:
        return []
    try:
        return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
    except (TypeError, ValueError):
        return []


def union_bbox(left: Any, right: Any) -> list[float]:
    a = normalize_bbox(left)
    b = normalize_bbox(right)
    if not a:
        return b
    if not b:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def merge_source_refs(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in [*left, *right]:
        key = repr(sorted(ref.items())) if isinstance(ref, dict) else repr(ref)
        if key in seen:
            continue
        seen.add(key)
        if isinstance(ref, dict):
            output.append(ref)
    return output


def dedupe_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for annotation in annotations:
        key = semantic_text_key(annotation.get("content", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(annotation)
    return output


def dedupe_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for relation in relations:
        key = (normalized_key(relation.get("target_title", "")), str(relation.get("relation_type") or "references"))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        output.append(relation)
    return output


def node_text(item: dict[str, Any]) -> str:
    return normalize_display_text(item.get("text") or item.get("content") or item.get("title") or item.get("label") or "")


def normalize_condition(value: Any) -> str:
    normalized = normalized_text(str(value or "next"))
    if normalized in {"yes", "y", "co", "dung", "true"}:
        return "yes"
    if normalized in {"no", "n", "khong", "sai", "false"}:
        return "no"
    if normalized in VALID_EDGE_CONDITIONS:
        return normalized
    return "next"


def normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalized_text(str(value or ""))).strip("_")


def normalized_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFD", value or "").replace("đ", "d").replace("Đ", "D")
    ascii_value = "".join(char for char in ascii_value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9?]+", " ", ascii_value.lower()).strip()


def semantic_text_key(value: Any) -> str:
    return " ".join(normalized_text(str(value or "")).split()[:18])


def normalize_display_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def metadata_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def list_payload(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_or_default(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
