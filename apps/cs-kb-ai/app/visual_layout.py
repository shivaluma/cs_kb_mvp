from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image


def extract_pdf_visual_layout(
    data: bytes,
    filename: str,
    *,
    max_pages: int = 3,
    scale: float = 2.0,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    rendered_pages, render_warnings = render_pdf_pages(data, max_pages=max_pages, scale=scale)
    warnings.extend(render_warnings)
    if not rendered_pages:
        return {}, warnings or ["visual_layout_render_failed"]

    pages: list[dict[str, Any]] = []
    total_shapes = 0
    total_connectors = 0
    total_edges = 0
    for page in rendered_pages:
        page_warnings: list[str] = []
        text_blocks = page.get("text_blocks", [])
        image = page["image"]
        shape_candidates, shape_warnings = detect_shape_candidates(image, text_blocks, int(page["page"]))
        connector_candidates, connector_warnings = detect_connector_candidates(image, shape_candidates, text_blocks, int(page["page"]))
        page_warnings.extend(shape_warnings)
        page_warnings.extend(connector_warnings)
        graph_candidate = build_visual_graph_candidate(shape_candidates, connector_candidates, int(page["page"]))
        total_shapes += len(shape_candidates)
        total_connectors += len(connector_candidates)
        total_edges += len(graph_candidate.get("edge_candidates", []))
        pages.append(
            {
                "page": page["page"],
                "image_size": page["image_size"],
                "text_blocks": compact_text_blocks(text_blocks),
                "shape_candidates": shape_candidates[:120],
                "connector_candidates": connector_candidates[:160],
                "graph_candidate": graph_candidate,
                "warnings": page_warnings[:20],
            }
        )

    return (
        {
            "filename": filename,
            "source_type": "pdf_visual_layout",
            "pages": pages,
            "summary": {
                "page_count": len(pages),
                "shape_candidate_count": total_shapes,
                "connector_candidate_count": total_connectors,
                "edge_candidate_count": total_edges,
                "confidence": visual_layout_confidence(total_shapes, total_edges),
            },
        },
        warnings,
    )


def render_pdf_pages(data: bytes, *, max_pages: int, scale: float) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import fitz  # type: ignore
    except Exception:
        return render_pdf_pages_with_pdfium(data, max_pages=max_pages, scale=scale)

    warnings: list[str] = []
    pages: list[dict[str, Any]] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        for page_index in range(min(len(doc), max_pages)):
            page = doc[page_index]
            matrix = fitz.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
            text_blocks = extract_fitz_text_blocks(page, scale, page_index + 1)
            pages.append(
                {
                    "page": page_index + 1,
                    "image": image,
                    "image_size": [image.width, image.height],
                    "text_blocks": text_blocks,
                }
            )
        if not pages:
            warnings.append("visual_layout_render_empty")
        else:
            warnings.append(f"visual_layout_pages_rendered:{len(pages)}")
        return pages, warnings
    except Exception as exc:
        fallback_pages, fallback_warnings = render_pdf_pages_with_pdfium(data, max_pages=max_pages, scale=scale)
        return fallback_pages, [f"visual_layout_fitz_failed:{exc.__class__.__name__}", *fallback_warnings]


def render_pdf_pages_with_pdfium(data: bytes, *, max_pages: int, scale: float) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return [], ["visual_layout_render_unavailable:pypdfium2_missing"]

    try:
        pdf = pdfium.PdfDocument(data)
        pages: list[dict[str, Any]] = []
        for page_index in range(min(len(pdf), max_pages)):
            page = pdf[page_index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            pages.append(
                {
                    "page": page_index + 1,
                    "image": image,
                    "image_size": [image.width, image.height],
                    "text_blocks": [],
                }
            )
        if not pages:
            return [], ["visual_layout_render_empty"]
        return pages, [f"visual_layout_pages_rendered_without_text_bboxes:{len(pages)}"]
    except Exception as exc:
        return [], [f"visual_layout_render_failed:{exc.__class__.__name__}"]


def extract_fitz_text_blocks(page: Any, scale: float, page_number: int) -> list[dict[str, Any]]:
    text_blocks: list[dict[str, Any]] = []
    try:
        payload = page.get_text("dict")
    except Exception:
        return text_blocks
    for block_index, block in enumerate(payload.get("blocks", [])):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        bboxes: list[list[float]] = []
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not line_text:
                continue
            lines.append(line_text)
            bbox = line.get("bbox")
            if bbox:
                bboxes.append(scale_bbox(bbox, scale))
        text = "\n".join(lines).strip()
        if not text:
            continue
        bbox = union_bboxes(bboxes) if bboxes else scale_bbox(block.get("bbox", [0, 0, 0, 0]), scale)
        text_blocks.append(
            {
                "id": f"p{page_number}_text_{block_index}",
                "page": page_number,
                "text": text,
                "bbox": bbox,
            }
        )
    return text_blocks


def detect_shape_candidates(image: Image.Image, text_blocks: list[dict[str, Any]], page_number: int) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return [], ["visual_shape_detection_unavailable:opencv_missing"]

    image_array = np.array(image)
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[dict[str, Any]] = []
    image_area = image.width * image.height
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 600 or area > image_area * 0.25:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 36 or h < 18 or w > image.width * 0.36 or h > image.height * 0.42:
            continue
        if h / max(1, w) > 3.5 and x < image.width * 0.08:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.035 * perimeter, True)
        if len(approx) < 4 or len(approx) > 12:
            continue
        bbox = [float(x), float(y), float(x + w), float(y + h)]
        if any(iou_bbox(bbox, existing["bbox"]) > 0.65 for existing in candidates):
            continue
        shape_type = classify_shape(approx.reshape(-1, 2).tolist(), bbox)
        contained_text = text_inside_bbox(text_blocks, bbox)
        if not contained_text and shape_type != "decision_candidate":
            continue
        confidence = 0.68 if contained_text else 0.48
        if shape_type == "decision_candidate":
            confidence += 0.08
        candidates.append(
            {
                "id": f"p{page_number}_node_{len(candidates) + 1}",
                "page": page_number,
                "shape_type": shape_type,
                "bbox": bbox,
                "text": contained_text[:600],
                "confidence": round(min(confidence, 0.9), 2),
            }
        )
    candidates = prune_container_shapes(candidates)
    candidates.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    for index, candidate in enumerate(candidates, start=1):
        candidate["id"] = f"p{page_number}_node_{index}"
    return candidates[:160], [f"visual_shape_candidates:{len(candidates)}"]


def prune_container_shapes(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_area = bbox_area(candidate["bbox"])
        contains_children = [
            other for other in candidates
            if other is not candidate
            and candidate_area > bbox_area(other["bbox"]) * 1.4
            and bbox_contains_bbox(candidate["bbox"], other["bbox"], padding=4)
        ]
        if candidate.get("shape_type") != "decision_candidate" and len(contains_children) >= 2:
            continue
        output.append(candidate)
    return output


def detect_connector_candidates(
    image: Image.Image,
    shapes: list[dict[str, Any]],
    text_blocks: list[dict[str, Any]],
    page_number: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return [], ["visual_connector_detection_unavailable:opencv_missing"]
    if len(shapes) < 2:
        return [], ["visual_connector_detection_skipped:not_enough_nodes"]

    image_array = np.array(image)
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 160)
    min_line_length = max(24, min(image.width, image.height) // 40)
    raw_lines = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=55, minLineLength=min_line_length, maxLineGap=10)
    if raw_lines is None:
        return [], ["visual_connector_candidates:0"]

    connectors: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int]] = set()
    max_distance = max(32.0, min(image.width, image.height) * 0.035)
    for raw_line in raw_lines[:900]:
        x1, y1, x2, y2 = [int(value) for value in raw_line[0]]
        line_length = math.dist((x1, y1), (x2, y2))
        if line_length < min_line_length:
            continue
        if line_length > max(image.width, image.height) * 0.45:
            continue
        key = normalized_line_key(x1, y1, x2, y2)
        if key in seen:
            continue
        seen.add(key)
        start_shape, start_distance = nearest_shape((x1, y1), shapes)
        end_shape, end_distance = nearest_shape((x2, y2), shapes)
        if not start_shape or not end_shape or start_shape["id"] == end_shape["id"]:
            continue
        if start_distance > max_distance or end_distance > max_distance:
            continue
        from_shape, to_shape, direction_reason = orient_connector(start_shape, end_shape, (x1, y1), (x2, y2))
        condition = nearest_condition_label(text_blocks, [x1, y1, x2, y2])
        confidence = 0.42
        if condition in {"yes", "no"}:
            confidence += 0.12
        if direction_reason != "geometric_guess":
            confidence += 0.08
        connectors.append(
            {
                "id": f"p{page_number}_connector_{len(connectors) + 1}",
                "page": page_number,
                "from_node": from_shape["id"],
                "to_node": to_shape["id"],
                "condition": condition or "next",
                "bbox": line_bbox(x1, y1, x2, y2),
                "confidence": round(min(confidence, 0.68), 2),
                "direction_reason": direction_reason,
                "review_status": "needs_review",
            }
        )
    connectors = dedupe_connectors(connectors)
    return connectors[:240], [f"visual_connector_candidates:{len(connectors)}"]


def build_visual_graph_candidate(
    shape_candidates: list[dict[str, Any]],
    connector_candidates: list[dict[str, Any]],
    page_number: int,
) -> dict[str, Any]:
    nodes = [
        {
            "id": shape["id"],
            "page": page_number,
            "type": visual_node_type(shape),
            "title": shape.get("text") or shape["shape_type"].replace("_candidate", ""),
            "bbox": shape["bbox"],
            "confidence": shape["confidence"],
        }
        for shape in shape_candidates
        if shape.get("text") or shape["shape_type"] == "decision_candidate"
    ]
    node_ids = {node["id"] for node in nodes}
    edge_candidates = [
        edge for edge in connector_candidates
        if edge.get("from_node") in node_ids and edge.get("to_node") in node_ids
    ]
    return {
        "page": page_number,
        "nodes": nodes[:120],
        "edge_candidates": edge_candidates[:200],
        "graph_confidence": visual_graph_confidence(nodes, edge_candidates),
        "requires_human_review": True,
        "review_reason": "Visual detector creates candidate topology only; decision branches must be reviewed against the source diagram before publish.",
    }


def compact_visual_context(visual_layout: dict[str, Any], *, max_nodes: int = 80, max_edges: int = 120) -> dict[str, Any]:
    pages = []
    semantic_refinement = visual_layout.get("semantic_refinement") if isinstance(visual_layout.get("semantic_refinement"), dict) else {}
    semantic_pages = semantic_refinement.get("pages") if isinstance(semantic_refinement.get("pages"), list) else []
    for page in visual_layout.get("pages", [])[:3]:
        graph = page.get("graph_candidate") if isinstance(page, dict) else {}
        if not isinstance(graph, dict):
            graph = {}
        semantic_page = next(
            (
                item for item in semantic_pages
                if isinstance(item, dict) and item.get("page") == page.get("page")
            ),
            {},
        )
        pages.append(
            {
                "page": page.get("page"),
                "image_size": page.get("image_size"),
                "nodes": graph.get("nodes", [])[:max_nodes],
                "edge_candidates": graph.get("edge_candidates", [])[:max_edges],
                "semantic_nodes": (semantic_page.get("semantic_nodes", []) if isinstance(semantic_page, dict) else [])[:max_nodes],
                "semantic_annotations": (semantic_page.get("annotations", []) if isinstance(semantic_page, dict) else [])[:max_nodes],
                "semantic_uncertain_edges": (semantic_page.get("uncertain_edges", []) if isinstance(semantic_page, dict) else [])[:max_edges],
                "graph_confidence": graph.get("graph_confidence", 0),
                "review_reason": graph.get("review_reason", ""),
            }
        )
    payload = {
        "source_type": visual_layout.get("source_type", "pdf_visual_layout"),
        "summary": visual_layout.get("summary", {}),
        "pages": pages,
        "rules": [
            "Use edge_candidates as topology evidence; do not infer edges from text order.",
            "Low-confidence edge candidates should become uncertain_edges unless visually confirmed by the image.",
            "Use node bbox as source_refs.bbox when creating node-derived units.",
            "Notes/scripts/warnings should be annotations unless they are actual flow steps.",
        ],
    }
    if semantic_refinement:
        graph_candidate = semantic_refinement.get("workflow_graph_candidate") if isinstance(semantic_refinement.get("workflow_graph_candidate"), dict) else {}
        payload["semantic_refinement"] = {
            "summary": semantic_refinement.get("summary", {}),
            "workflow_graph_candidate": {
                "lanes": graph_candidate.get("lanes", []),
                "nodes": graph_candidate.get("nodes", [])[:max_nodes],
                "edges": graph_candidate.get("edges", [])[:max_edges],
                "annotations": graph_candidate.get("annotations", [])[:max_nodes],
                "warnings": graph_candidate.get("warnings", [])[:max_nodes],
                "uncertain_edges": graph_candidate.get("uncertain_edges", [])[:max_edges],
                "graph_confidence": graph_candidate.get("graph_confidence", 0),
                "topology_review_required": graph_candidate.get("topology_review_required", True),
            },
            "validation_errors": semantic_refinement.get("validation_errors", [])[:40],
        }
    return payload


def compact_text_blocks(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": block.get("id"),
            "page": block.get("page"),
            "text": str(block.get("text") or "")[:400],
            "bbox": block.get("bbox", []),
        }
        for block in text_blocks[:100]
    ]


def scale_bbox(bbox: Any, scale: float) -> list[float]:
    try:
        x1, y1, x2, y2 = [float(value) * scale for value in bbox]
        return [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]
    except Exception:
        return [0.0, 0.0, 0.0, 0.0]


def union_bboxes(bboxes: list[list[float]]) -> list[float]:
    if not bboxes:
        return [0.0, 0.0, 0.0, 0.0]
    return [
        round(min(bbox[0] for bbox in bboxes), 2),
        round(min(bbox[1] for bbox in bboxes), 2),
        round(max(bbox[2] for bbox in bboxes), 2),
        round(max(bbox[3] for bbox in bboxes), 2),
    ]


def classify_shape(points: list[list[int]], bbox: list[float]) -> str:
    if len(points) == 4:
        x1, y1, x2, y2 = bbox
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        corner_hits = 0
        midpoint_hits = 0
        for x, y in points:
            near_x_corner = min(abs(x - x1), abs(x - x2)) < width * 0.18
            near_y_corner = min(abs(y - y1), abs(y - y2)) < height * 0.18
            near_x_mid = abs(x - (x1 + x2) / 2) < width * 0.25
            near_y_mid = abs(y - (y1 + y2) / 2) < height * 0.25
            corner_hits += int(near_x_corner and near_y_corner)
            midpoint_hits += int((near_x_mid and near_y_corner) or (near_y_mid and near_x_corner))
        if midpoint_hits >= 3 and corner_hits <= 1:
            return "decision_candidate"
        return "action_candidate"
    if len(points) > 6:
        return "start_end_candidate"
    return "shape_candidate"


def text_inside_bbox(text_blocks: list[dict[str, Any]], bbox: list[float]) -> str:
    texts = []
    for block in text_blocks:
        block_bbox = block.get("bbox")
        if not isinstance(block_bbox, list) or len(block_bbox) != 4:
            continue
        if bbox_contains_center(bbox, block_bbox) or iou_bbox(bbox, block_bbox) > 0.08:
            text = str(block.get("text") or "").strip()
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def bbox_contains_center(container: list[float], inner: list[float]) -> bool:
    cx = (inner[0] + inner[2]) / 2
    cy = (inner[1] + inner[3]) / 2
    return container[0] <= cx <= container[2] and container[1] <= cy <= container[3]


def bbox_contains_bbox(container: list[float], inner: list[float], *, padding: float = 0) -> bool:
    return (
        container[0] - padding <= inner[0]
        and container[1] - padding <= inner[1]
        and container[2] + padding >= inner[2]
        and container[3] + padding >= inner[3]
    )


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def iou_bbox(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def nearest_shape(point: tuple[int, int], shapes: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    best_shape: dict[str, Any] | None = None
    best_distance = float("inf")
    for shape in shapes:
        distance = distance_to_bbox(point, shape["bbox"])
        if distance < best_distance:
            best_shape = shape
            best_distance = distance
    return best_shape, best_distance


def distance_to_bbox(point: tuple[int, int], bbox: list[float]) -> float:
    x, y = point
    dx = max(bbox[0] - x, 0, x - bbox[2])
    dy = max(bbox[1] - y, 0, y - bbox[3])
    if dx == 0 and dy == 0:
        distances = [abs(x - bbox[0]), abs(x - bbox[2]), abs(y - bbox[1]), abs(y - bbox[3])]
        return min(distances)
    return math.hypot(dx, dy)


def normalized_line_key(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    values = [round(x1 / 8), round(y1 / 8), round(x2 / 8), round(y2 / 8)]
    forward = tuple(values)
    reverse = tuple(values[2:] + values[:2])
    return min(forward, reverse)


def orient_connector(
    start_shape: dict[str, Any],
    end_shape: dict[str, Any],
    start_point: tuple[int, int],
    end_point: tuple[int, int],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    start_center = bbox_center(start_shape["bbox"])
    end_center = bbox_center(end_shape["bbox"])
    dx = end_center[0] - start_center[0]
    dy = end_center[1] - start_center[1]
    if abs(dx) > abs(dy) * 1.4:
        return (start_shape, end_shape, "left_to_right_geometric_guess") if dx > 0 else (end_shape, start_shape, "left_to_right_geometric_guess")
    if abs(dy) > abs(dx) * 1.2:
        return (start_shape, end_shape, "top_to_bottom_geometric_guess") if dy > 0 else (end_shape, start_shape, "top_to_bottom_geometric_guess")
    line_dx = end_point[0] - start_point[0]
    line_dy = end_point[1] - start_point[1]
    if abs(line_dx) + abs(line_dy) > 0:
        return (start_shape, end_shape, "geometric_guess") if line_dx + line_dy >= 0 else (end_shape, start_shape, "geometric_guess")
    return start_shape, end_shape, "geometric_guess"


def bbox_center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def nearest_condition_label(text_blocks: list[dict[str, Any]], line: list[int]) -> str:
    if not text_blocks:
        return ""
    bbox = expand_bbox(line_bbox(*line), 32)
    candidates: list[tuple[float, str]] = []
    for block in text_blocks:
        text = str(block.get("text") or "").strip().lower()
        if not text:
            continue
        block_bbox = block.get("bbox")
        if not isinstance(block_bbox, list) or len(block_bbox) != 4:
            continue
        if not bbox_intersects(bbox, block_bbox):
            continue
        normalized = text.replace("có", "yes").replace("co", "yes").replace("không", "no").replace("khong", "no")
        if "yes" in normalized:
            candidates.append((bbox_distance(bbox, block_bbox), "yes"))
        elif "no" in normalized:
            candidates.append((bbox_distance(bbox, block_bbox), "no"))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[0][1]


def line_bbox(x1: int, y1: int, x2: int, y2: int) -> list[float]:
    return [float(min(x1, x2)), float(min(y1, y2)), float(max(x1, x2)), float(max(y1, y2))]


def expand_bbox(bbox: list[float], amount: float) -> list[float]:
    return [bbox[0] - amount, bbox[1] - amount, bbox[2] + amount, bbox[3] + amount]


def bbox_intersects(left: list[float], right: list[float]) -> bool:
    return not (left[2] < right[0] or right[2] < left[0] or left[3] < right[1] or right[3] < left[1])


def bbox_distance(left: list[float], right: list[float]) -> float:
    return math.dist(bbox_center(left), bbox_center(right))


def dedupe_connectors(connectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_pair: dict[tuple[str, str, str], dict[str, Any]] = {}
    for connector in connectors:
        key = (connector["from_node"], connector["to_node"], connector.get("condition") or "next")
        existing = best_by_pair.get(key)
        if not existing or float(connector.get("confidence") or 0) > float(existing.get("confidence") or 0):
            best_by_pair[key] = connector
    output = list(best_by_pair.values())
    output.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    for index, item in enumerate(output, start=1):
        item["id"] = f"p{item['page']}_connector_{index}"
    return output


def visual_node_type(shape: dict[str, Any]) -> str:
    shape_type = shape.get("shape_type")
    if shape_type == "decision_candidate":
        return "decision"
    if shape_type == "start_end_candidate":
        text = str(shape.get("text") or "").lower()
        return "end" if "end" in text else "start"
    return "action"


def visual_layout_confidence(shape_count: int, edge_count: int) -> float:
    if shape_count >= 4 and edge_count >= 3:
        return 0.62
    if shape_count >= 2:
        return 0.48
    return 0.25


def visual_graph_confidence(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> float:
    if not nodes:
        return 0.0
    edge_ratio = min(1.0, len(edges) / max(1, len(nodes) - 1))
    text_ratio = sum(1 for node in nodes if node.get("title")) / len(nodes)
    return round(min(0.72, 0.25 + edge_ratio * 0.25 + text_ratio * 0.22), 2)
