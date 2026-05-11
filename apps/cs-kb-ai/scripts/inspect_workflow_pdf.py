from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.ingestion import build_workflow_semantic_refinement
from app.text_processing import classify_document
from app.visual_layout import extract_pdf_visual_layout


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect local workflow PDF visual and semantic extraction.")
    parser.add_argument("pdf", help="Path to the workflow PDF")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Print the full semantic refinement JSON")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser()
    data = pdf_path.read_bytes()
    visual_layout, warnings = extract_pdf_visual_layout(data, pdf_path.name, max_pages=args.max_pages)
    classification = classify_document(pdf_path.name, "application/pdf", "workflow diagram")
    refinement = build_workflow_semantic_refinement(
        filename=pdf_path.name,
        visual_layout=visual_layout,
        source_blocks=[],
        classification=classification,
    )

    if args.json:
        print(json.dumps({"warnings": warnings, "semantic_refinement": refinement}, ensure_ascii=False, indent=2))
        return

    graph = refinement.get("workflow_graph_candidate") if isinstance(refinement.get("workflow_graph_candidate"), dict) else {}
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    annotations = graph.get("annotations") if isinstance(graph.get("annotations"), list) else []
    uncertain_edges = graph.get("uncertain_edges") if isinstance(graph.get("uncertain_edges"), list) else []
    print(f"warnings: {warnings}")
    print(f"summary: {json.dumps(refinement.get('summary', {}), ensure_ascii=False)}")
    print(f"nodes={len(nodes)} annotations={len(annotations)} uncertain_edges={len(uncertain_edges)}")
    for node in nodes:
        if not isinstance(node, dict):
            continue
        print(format_node(node))


def format_node(node: dict[str, Any]) -> str:
    question = str(node.get("question") or "").strip()
    content = str(node.get("content") or "").strip()
    return "\n".join(
        [
            f"--- {node.get('id')} | graph_type={node.get('type')} | semantic={node.get('semantic_node_type')}",
            f"title: {node.get('title')}",
            f"question: {question}",
            f"content:\n{content}",
        ]
    )


if __name__ == "__main__":
    main()
