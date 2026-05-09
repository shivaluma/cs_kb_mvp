from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


SYSTEM_PROMPT = """You extract customer-support SOP drafts from messy source documents.
Rules:
- Extract only facts present in the source text.
- Do not create policy, refund rules, security rules, or workflow branches not present in the source.
- Output JSON only.
- Every unit must be reviewable by CS Ops and must not be considered approved.
- Prefer granular operational units: workflow_overview, verification_dependency, workflow_step, decision_point, macro_script, operational_note, security_note, related_document.
"""


def enabled() -> bool:
    return bool(settings.openrouter_api_key.strip())


def extract_workflow_units(filename: str, raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled():
        return [], ["openrouter_disabled"]

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extract a structured draft workflow from this CS SOP document. "
                    "Return JSON with shape {\"units\":[{\"unit_type\":\"...\",\"title\":\"...\","
                    "\"content\":\"...\",\"confidence\":0.0,\"metadata\":{...}}]}. "
                    "For decision points, include condition/yes_next/no_next when available. "
                    "For scripts, preserve the channel and copyable script text. "
                    "For security notes, set metadata.risk_level=\"high\".\n\n"
                    f"Filename: {filename}\n\nSource text:\n{raw_text[:18000]}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_app_url,
        "X-Title": "CS SOP Knowledge Base",
    }

    try:
        with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
            response = client.post(
                f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        units = parsed.get("units") if isinstance(parsed, dict) else None
        if not isinstance(units, list):
            return [], ["openrouter_invalid_units"]
        normalized = [normalize_unit(unit) for unit in units if isinstance(unit, dict)]
        return [unit for unit in normalized if unit["content"]], ["openrouter_extraction_used"]
    except Exception as exc:
        return [], [f"openrouter_extraction_failed:{exc.__class__.__name__}"]


def normalize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
    confidence = unit.get("confidence", 0.72)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.72
    return {
        "unit_type": str(unit.get("unit_type") or "workflow_step"),
        "title": str(unit.get("title") or "Extracted workflow unit").strip()[:180],
        "content": str(unit.get("content") or "").strip(),
        "confidence": max(0.0, min(confidence_value, 1.0)),
        "metadata": metadata,
    }
