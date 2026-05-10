from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


AI_BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:8090").rstrip("/")


@dataclass(frozen=True)
class GoldenQuery:
    query: str
    expected_unit_types: tuple[str, ...]
    expected_terms: tuple[str, ...]


GOLDEN_QUERIES = [
    GoldenQuery("SLA chat social", ("sla_rule",), ("30", "phút")),
    GoldenQuery("Pancake lấy chat", ("operational_instruction", "routing_rule"), ("pancake",)),
    GoldenQuery("2 agent cùng trả lời", ("policy_rule",), ("agent", "trả lời")),
    GoldenQuery("không có SĐT tạo case social", ("case_creation_rule",), ("84912345678", "case")),
    GoldenQuery("SI OB source internal", ("handoff_rule",), ("si", "ob", "source internal")),
    GoldenQuery("danh xưng Be và bạn", ("macro_script", "operational_note"), ("be", "bạn")),
    GoldenQuery("QA audit Pancake", ("operational_note",), ("qa", "pancake")),
]


def main() -> int:
    results = []
    passed = 0
    with httpx.Client(timeout=20) as client:
        for item in GOLDEN_QUERIES:
            response = client.post(
                f"{AI_BASE_URL}/ai/v1/retrieve",
                json={
                    "query": item.query,
                    "limit": 5,
                    "mode": "hybrid",
                    "filters": {"status": ["published"]},
                },
            )
            response.raise_for_status()
            payload = response.json()
            evaluation = evaluate_query(item, payload.get("results", []))
            passed += 1 if evaluation["passed"] else 0
            results.append(evaluation)

    output = {
        "suite": "chat_social_lookup",
        "base_url": AI_BASE_URL,
        "passed": passed,
        "total": len(GOLDEN_QUERIES),
        "pass_rate": round(passed / len(GOLDEN_QUERIES), 3),
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if passed == len(GOLDEN_QUERIES) else 1


def evaluate_query(item: GoldenQuery, results: list[dict[str, Any]]) -> dict[str, Any]:
    top = results[:5]
    matched = None
    for index, result in enumerate(top, start=1):
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        unit_type = str(metadata.get("unit_type") or result.get("section") or "")
        haystack = " ".join(
            [
                unit_type,
                str(result.get("heading") or ""),
                str(result.get("content") or ""),
                json.dumps(metadata, ensure_ascii=False),
            ]
        ).lower()
        has_type = unit_type in item.expected_unit_types
        has_terms = all(term.lower() in haystack for term in item.expected_terms)
        if has_type and has_terms:
            matched = {
                "rank": index,
                "unit_type": unit_type,
                "heading": result.get("heading"),
                "score": result.get("score"),
                "chunk_id": result.get("chunk_id"),
            }
            break

    return {
        "query": item.query,
        "expected_unit_types": item.expected_unit_types,
        "expected_terms": item.expected_terms,
        "passed": matched is not None,
        "matched": matched,
        "top_results": [
            {
                "rank": index,
                "unit_type": (result.get("metadata") or {}).get("unit_type") if isinstance(result.get("metadata"), dict) else result.get("section"),
                "heading": result.get("heading"),
                "score": result.get("score"),
            }
            for index, result in enumerate(top, start=1)
        ],
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.ConnectError:
        print(f"Cannot connect to {AI_BASE_URL}. Start the AI service first.", file=sys.stderr)
        raise SystemExit(2)
