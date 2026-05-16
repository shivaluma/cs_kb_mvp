from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("policy_taxonomy.json")


def taxonomy_path() -> Path:
    configured = os.getenv("CS_AI_POLICY_TAXONOMY_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_TAXONOMY_PATH


@lru_cache(maxsize=4)
def load_policy_taxonomy(path_text: str = "") -> dict[str, Any]:
    path = Path(path_text) if path_text else taxonomy_path()
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}
    return payload if isinstance(payload, dict) else {}


def policy_taxonomy() -> dict[str, Any]:
    return load_policy_taxonomy(str(taxonomy_path()))


def taxonomy_section(key: str) -> dict[str, Any]:
    value = policy_taxonomy().get(key)
    return value if isinstance(value, dict) else {}


def taxonomy_patterns(key: str) -> dict[str, tuple[str, ...]]:
    value = taxonomy_section(key)
    output: dict[str, tuple[str, ...]] = {}
    for group_key, terms in value.items():
        if isinstance(terms, list):
            output[str(group_key)] = tuple(str(term) for term in terms if str(term).strip())
    return output


def taxonomy_string_list(key: str) -> tuple[str, ...]:
    value = policy_taxonomy().get(key)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def taxonomy_mapping(key: str) -> dict[str, tuple[str, ...]]:
    value = taxonomy_section(key)
    output: dict[str, tuple[str, ...]] = {}
    for group_key, items in value.items():
        if isinstance(items, list):
            output[str(group_key)] = tuple(str(item) for item in items if str(item).strip())
    return output


def taxonomy_score_map(key: str) -> dict[str, float]:
    value = taxonomy_section(key)
    output: dict[str, float] = {}
    for item_key, item_value in value.items():
        try:
            output[str(item_key)] = float(item_value)
        except (TypeError, ValueError):
            continue
    return output


def taxonomy_text(key: str, default: str = "") -> str:
    value = policy_taxonomy().get(key)
    return str(value) if isinstance(value, str) else default


def nested_taxonomy_text(section: str, key: str, default: str = "") -> str:
    item = taxonomy_section(section).get(key)
    return str(item) if isinstance(item, str) else default


def nested_taxonomy_string_list(section: str, key: str) -> tuple[str, ...]:
    item = taxonomy_section(section).get(key)
    if not isinstance(item, list):
        return ()
    return tuple(str(value) for value in item if str(value).strip())


def nested_taxonomy_mapping(section: str, key: str) -> dict[str, tuple[str, ...]]:
    item = taxonomy_section(section).get(key)
    if not isinstance(item, dict):
        return {}
    output: dict[str, tuple[str, ...]] = {}
    for item_key, values in item.items():
        if isinstance(values, list):
            output[str(item_key)] = tuple(str(value) for value in values if str(value).strip())
    return output


def nested_taxonomy_score_map(section: str, key: str) -> dict[str, float]:
    item = taxonomy_section(section).get(key)
    if not isinstance(item, dict):
        return {}
    output: dict[str, float] = {}
    for item_key, value in item.items():
        try:
            output[str(item_key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def clear_policy_taxonomy_cache() -> None:
    load_policy_taxonomy.cache_clear()
