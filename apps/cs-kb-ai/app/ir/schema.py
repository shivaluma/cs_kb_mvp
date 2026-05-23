from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def excerpt_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@dataclass
class Provenance:
    parser_name: str
    parser_version: str
    extraction_method: str
    source_locator: dict[str, Any] = field(default_factory=dict)
    raw_excerpt_hash: str = ""
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentArtifact:
    artifact_id: str
    sha256: str
    mime_type: str
    extension: str
    original_filename: str
    parser_versions: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Container:
    container_id: str
    kind: str
    parent_id: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    bbox: list[float] | None = None
    order_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceElement:
    element_id: str
    kind: str
    container_id: str
    text: str = ""
    html: str = ""
    value: Any = None
    formula: str = ""
    normalized_value: Any = None
    bbox: list[float] | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None
    row_index: int | None = None
    col_index: int | None = None
    style: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown", "v0", "deterministic"))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = self.provenance.to_dict()
        return payload


@dataclass
class Relation:
    relation_id: str
    kind: str
    source_id: str
    target_id: str
    confidence: float = 1.0
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown", "v0", "deterministic"))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = self.provenance.to_dict()
        return payload


@dataclass
class SemanticUnit:
    unit_id: str
    unit_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    source_element_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    validation_status: str = "pending"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceChunk:
    chunk_id: str
    chunk_type: str
    text: str
    source_unit_ids: list[str] = field(default_factory=list)
    source_element_ids: list[str] = field(default_factory=list)
    evidence_hash: str = ""
    confidence: float = 1.0
    publish_eligible: bool = True
    blocked_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentEvidenceGraph:
    artifact: DocumentArtifact
    containers: list[Container] = field(default_factory=list)
    source_elements: list[SourceElement] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    semantic_units: list[SemanticUnit] = field(default_factory=list)
    chunks: list[EvidenceChunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def element_map(self) -> dict[str, SourceElement]:
        return {element.element_id: element for element in self.source_elements}

    def elements_for_ids(self, element_ids: list[str]) -> list[SourceElement]:
        elements = self.element_map()
        return [elements[element_id] for element_id in element_ids if element_id in elements]

    def evidence_hash(self, element_ids: list[str]) -> str:
        elements = [element.to_dict() for element in self.elements_for_ids(element_ids)]
        if not elements:
            return ""
        return stable_hash(elements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "containers": [container.to_dict() for container in self.containers],
            "source_elements": [element.to_dict() for element in self.source_elements],
            "relations": [relation.to_dict() for relation in self.relations],
            "semantic_units": [unit.to_dict() for unit in self.semantic_units],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "metadata": self.metadata,
        }
