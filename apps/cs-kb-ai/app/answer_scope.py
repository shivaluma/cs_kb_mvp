from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from app.policy_taxonomy import (
    nested_taxonomy_mapping,
    nested_taxonomy_score_map,
    nested_taxonomy_string_list,
    nested_taxonomy_text,
    taxonomy_mapping,
    taxonomy_patterns,
    taxonomy_score_map,
    taxonomy_section,
    taxonomy_string_list,
)


PatternMap = dict[str, tuple[str, ...]]


def asked_field_patterns() -> PatternMap:
    return taxonomy_patterns("asked_field_patterns")


def explicit_condition_patterns() -> PatternMap:
    return taxonomy_patterns("explicit_condition_patterns")


def branch_patterns() -> PatternMap:
    return taxonomy_patterns("branch_patterns")


def workflow_stage_patterns() -> PatternMap:
    return taxonomy_patterns("workflow_stage_patterns")


def channel_patterns() -> PatternMap:
    return taxonomy_patterns("channel_patterns")


def scenario_patterns() -> PatternMap:
    return taxonomy_patterns("scenario_patterns")


def negative_workflow_stages_by_scenario() -> dict[str, tuple[str, ...]]:
    return taxonomy_mapping("negative_workflow_stages_by_scenario")


def scope_rule_mapping(key: str) -> dict[str, tuple[str, ...]]:
    return nested_taxonomy_mapping("scope_rules", key)


def scope_rule_list(key: str) -> tuple[str, ...]:
    return nested_taxonomy_string_list("scope_rules", key)


def semantic_enrichment_mapping(key: str) -> dict[str, tuple[str, ...]]:
    return nested_taxonomy_mapping("semantic_enrichment", key)


def candidate_inference_mapping(key: str) -> dict[str, tuple[str, ...]]:
    return nested_taxonomy_mapping("candidate_inference_rules", key)


def candidate_inference_list(key: str) -> tuple[str, ...]:
    return nested_taxonomy_string_list("candidate_inference_rules", key)


def applicability_weights() -> dict[str, float]:
    return nested_taxonomy_score_map("applicability_scoring", "weights")


def applicability_thresholds() -> dict[str, float]:
    return nested_taxonomy_score_map("applicability_scoring", "thresholds")


def configured_policy_type_scores() -> dict[str, float]:
    return nested_taxonomy_score_map("applicability_scoring", "policy_type_scores")


def semantic_metadata_containers() -> tuple[str, ...]:
    return nested_taxonomy_string_list("semantic_metadata", "containers")


def semantic_metadata_keys(field: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    configured = nested_taxonomy_string_list("semantic_metadata", f"{field}_keys")
    return configured or fallback


@dataclass(frozen=True)
class AnswerScope:
    asked_fields: tuple[str, ...]
    explicit_conditions: tuple[str, ...]
    excluded_branch_types: tuple[str, ...]
    is_narrow: bool

    def model_dump(self) -> dict[str, Any]:
        return {
            "asked_fields": list(self.asked_fields),
            "explicit_conditions": list(self.explicit_conditions),
            "excluded_branch_types": list(self.excluded_branch_types),
            "is_narrow": self.is_narrow,
            "policy": (
                "Answer only the requested procedural field. Treat excluded_branch_types as "
                "supported-but-out-of-scope unless the question explicitly asks for them."
            ),
        }


@dataclass(frozen=True)
class PolicyFacets:
    asked_fields: tuple[str, ...]
    scenario_types: tuple[str, ...]
    workflow_stages: tuple[str, ...]
    negative_workflow_stages: tuple[str, ...]
    explicit_conditions: tuple[str, ...]
    channel_types: tuple[str, ...]
    case_types: tuple[str, ...]
    actors: tuple[str, ...]
    unsupported_sensitive: bool

    def model_dump(self) -> dict[str, Any]:
        return {
            "asked_fields": list(self.asked_fields),
            "scenario_types": list(self.scenario_types),
            "workflow_stages": list(self.workflow_stages),
            "negative_workflow_stages": list(self.negative_workflow_stages),
            "explicit_conditions": list(self.explicit_conditions),
            "channel_types": list(self.channel_types),
            "case_types": list(self.case_types),
            "actors": list(self.actors),
            "unsupported_sensitive": self.unsupported_sensitive,
        }


def build_answer_scope(question: str) -> AnswerScope:
    asked_fields = detect_pattern_keys(question, asked_field_patterns())
    explicit_conditions = detect_pattern_keys(question, explicit_condition_patterns())
    branch_mentions = detect_pattern_keys(question, branch_patterns())

    exclusions: set[str] = set()
    for asked_field in asked_fields:
        exclusions.update(scope_rule_mapping("asked_field_exclusions").get(asked_field, ()))
    for asked_field in asked_fields:
        exclusions.difference_update(scope_rule_mapping("asked_field_relaxes").get(asked_field, ()))
    exclusions.difference_update(explicit_conditions)
    exclusions.difference_update(branch_mentions)

    is_narrow = bool(set(asked_fields) & set(scope_rule_list("narrow_asked_fields"))) and not bool(
        set(asked_fields) & set(scope_rule_list("narrow_excluded_asked_fields"))
    )
    return AnswerScope(
        asked_fields=tuple(sorted(asked_fields)),
        explicit_conditions=tuple(sorted(explicit_conditions)),
        excluded_branch_types=tuple(sorted(exclusions)),
        is_narrow=is_narrow,
    )


def build_policy_facets(question: str, scope: AnswerScope | None = None) -> PolicyFacets:
    scope = scope or build_answer_scope(question)
    scenario_types = detect_pattern_keys(question, scenario_patterns())
    workflow_stages = detect_pattern_keys(question, workflow_stage_patterns())
    channel_types = detect_pattern_keys(question, channel_patterns())
    conditions = set(scope.explicit_conditions)
    actors = set()
    normalized = normalize_operational_text(question)
    for actor, patterns in semantic_enrichment_mapping("actor_patterns").items():
        if any(normalize_operational_text(pattern) in normalized for pattern in patterns):
            actors.add(actor)

    negative_stages: set[str] = set()
    negative_stage_map = negative_workflow_stages_by_scenario()
    for scenario in scenario_types:
        negative_stages.update(negative_stage_map.get(scenario, ()))
    asked_field_negative_stages = semantic_enrichment_mapping("asked_field_negative_workflow_stages")
    for asked_field in scope.asked_fields:
        negative_stages.update(asked_field_negative_stages.get(asked_field, ()))

    case_types = set()
    for scenario in scenario_types:
        workflow_stages.update(semantic_enrichment_mapping("scenario_workflow_stages").get(scenario, ()))
        case_types.update(semantic_enrichment_mapping("scenario_case_types").get(scenario, ()))
    condition_case_type_map = semantic_enrichment_mapping("condition_case_types")
    for condition in conditions:
        case_types.update(condition_case_type_map.get(condition, ()))

    return PolicyFacets(
        asked_fields=scope.asked_fields,
        scenario_types=tuple(sorted(scenario_types)),
        workflow_stages=tuple(sorted(workflow_stages)),
        negative_workflow_stages=tuple(sorted(negative_stages)),
        explicit_conditions=tuple(sorted(conditions)),
        channel_types=tuple(sorted(channel_types)),
        case_types=tuple(sorted(case_types)),
        actors=tuple(sorted(actors)),
        unsupported_sensitive=bool(scenario_types),
    )


def source_scope_metadata(text: str, scope: AnswerScope, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    branch_terms = detect_candidate_branch_types(text, metadata or {})
    unasked = sorted(branch_terms & set(scope.excluded_branch_types))
    return {
        "chat_scope_branch_terms": sorted(branch_terms),
        "chat_scope_unasked_branches": unasked,
        "chat_scope_asked_fields": list(scope.asked_fields),
        "chat_scope_narrow": scope.is_narrow,
    }


def scope_penalty(text: str, scope: AnswerScope, source_metadata: dict[str, Any] | None = None) -> tuple[float, list[str], dict[str, Any]]:
    metadata = source_scope_metadata(text, scope, source_metadata)
    unasked = metadata["chat_scope_unasked_branches"]
    if not unasked:
        return 0.0, [], metadata
    penalty = min(0.36, 0.12 * len(unasked))
    return penalty, [f"unasked_branch:{branch}" for branch in unasked], metadata


def policy_applicability_debug(
    *,
    query: str,
    candidate_text: str,
    metadata: dict[str, Any],
    scope: AnswerScope,
    facets: PolicyFacets,
    semantic_score: float,
    lexical_score: float,
) -> dict[str, Any]:
    candidate_stages = detect_candidate_workflow_stages(candidate_text, metadata)
    candidate_channels = detect_candidate_channels(candidate_text, metadata)
    candidate_conditions = detect_candidate_conditions(candidate_text, metadata)
    candidate_branches = detect_candidate_branch_types(candidate_text, metadata)
    candidate_negative_constraints = detect_candidate_negative_constraints(metadata)
    candidate_policy_type = candidate_policy_type_from_metadata(candidate_text, metadata)
    query_signals = (
        set(facets.workflow_stages)
        | set(facets.scenario_types)
        | set(facets.explicit_conditions)
        | set(facets.asked_fields)
        | set(facets.channel_types)
        | set(facets.case_types)
    )
    negative_violations = sorted((set(candidate_stages) & set(facets.negative_workflow_stages)) | (set(candidate_negative_constraints) & query_signals))
    scope_unasked = sorted(set(candidate_branches) & set(scope.excluded_branch_types))
    for branch in scope_unasked:
        if branch not in negative_violations:
            negative_violations.append(branch)

    workflow_score = workflow_match_score(facets, candidate_stages)
    condition_score = condition_entailment_score(facets, candidate_conditions, candidate_stages)
    policy_type_score = policy_type_score_for(candidate_policy_type, metadata)
    action_score = action_alignment_score(facets, candidate_channels, candidate_stages)
    negative_penalty = min(1.0, 0.34 * len(negative_violations))
    semantic_component = bounded_score(semantic_score)
    lexical_component = bounded_score(lexical_score / 5.0)
    weights = applicability_weights()

    applicability = (
        weights.get("semantic", 0.18) * semantic_component
        + weights.get("lexical", 0.12) * lexical_component
        + weights.get("condition", 0.25) * condition_score
        + weights.get("workflow", 0.18) * workflow_score
        + weights.get("policy_type", 0.12) * policy_type_score
        + weights.get("action", 0.15) * action_score
        - weights.get("negative_penalty", 0.32) * negative_penalty
    )
    applicability = round(max(0.0, min(applicability, 1.0)), 4)

    selected_because = []
    selected_signal_threshold = applicability_thresholds().get("selected_signal", 0.72)
    if workflow_score >= selected_signal_threshold:
        selected_because.append("workflow_stage_match")
    if condition_score >= selected_signal_threshold:
        selected_because.append("condition_match")
    if action_score >= selected_signal_threshold:
        selected_because.append("action_channel_match")
    if semantic_component >= 0.5 or lexical_component >= 0.5:
        selected_because.append("semantic_or_lexical_match")

    risk_flags = []
    if negative_violations:
        risk_flags.append("negative_constraint_violation")
    if candidate_policy_type in {"fallback_rule", "exception_rule", "downstream_step", "document_context"}:
        risk_flags.append(f"policy_type:{candidate_policy_type}")
    if workflow_score <= 0.25 and facets.workflow_stages:
        risk_flags.append("workflow_stage_mismatch")
    if condition_score <= 0.25 and facets.explicit_conditions:
        risk_flags.append("condition_mismatch")

    return {
        "policy_facets": facets.model_dump(),
        "candidate_policy_signals": {
            "policy_type": candidate_policy_type,
            "workflow_stages": candidate_stages,
            "channel_types": candidate_channels,
            "conditions": candidate_conditions,
            "branch_types": candidate_branches,
            "negative_constraints": candidate_negative_constraints,
        },
        "selected_because": selected_because,
        "risk_flags": risk_flags,
        "workflow_match_score": round(workflow_score, 4),
        "condition_entailment_score": round(condition_score, 4),
        "policy_type_score": round(policy_type_score, 4),
        "action_alignment_score": round(action_score, 4),
        "semantic_component_score": round(semantic_component, 4),
        "lexical_component_score": round(lexical_component, 4),
        "policy_applicability_score": applicability,
        "negative_constraint_violations": sorted(negative_violations),
    }


def detect_candidate_workflow_stages(text: str, metadata: dict[str, Any]) -> list[str]:
    stage_keys = semantic_metadata_keys("workflow_stage", ("workflow_stage", "workflow_stages", "stage", "stages"))
    metadata_values = metadata_terms(metadata, (*stage_keys, "policy_type", "branch_type", "answer_type", "tags", "section_path"))
    stages = detect_declared_semantic_values(metadata, stage_keys, workflow_stage_patterns().keys(), preserve_unknown=True)
    stages.update(detect_pattern_keys(" ".join([text, *metadata_values]), workflow_stage_patterns()))
    branch_terms = detect_candidate_branch_types(text, metadata)
    branch_stage_map = candidate_inference_mapping("branch_implied_workflow_stages")
    for branch in branch_terms:
        stages.update(branch_stage_map.get(branch, ()))
    return sorted(stages)


def detect_candidate_channels(text: str, metadata: dict[str, Any]) -> list[str]:
    channel_keys = semantic_metadata_keys("channel", ("channel", "channels", "channel_type", "channel_types"))
    metadata_values = metadata_terms(metadata, (*channel_keys, "tags", "aliases"))
    channels = detect_declared_semantic_values(metadata, channel_keys, channel_patterns().keys(), preserve_unknown=True)
    channels.update(detect_pattern_keys(" ".join([text, *metadata_values]), channel_patterns()))
    return sorted(channels)


def detect_candidate_conditions(text: str, metadata: dict[str, Any]) -> list[str]:
    condition_keys = semantic_metadata_keys("condition", ("condition", "conditions", "trigger", "triggers", "case_type", "case_types"))
    metadata_values = metadata_terms(metadata, (*condition_keys, "tags", "aliases"))
    allowed_conditions = set(explicit_condition_patterns()) | set(scenario_patterns())
    conditions = detect_declared_semantic_values(metadata, condition_keys, allowed_conditions, preserve_unknown=True)
    conditions.update(detect_pattern_keys(" ".join([text, *metadata_values]), explicit_condition_patterns()))
    conditions.update(detect_pattern_keys(" ".join([text, *metadata_values]), scenario_patterns()))
    return sorted(conditions)


def detect_candidate_branch_types(text: str, metadata: dict[str, Any]) -> set[str]:
    branch_keys = semantic_metadata_keys("branch", ("branch_type", "branch_types", "exception_type", "fallback_type"))
    metadata_values = metadata_terms(metadata, branch_keys)
    branches = detect_declared_semantic_values(metadata, branch_keys, branch_patterns().keys(), preserve_unknown=True)
    branches.update(detect_pattern_keys(" ".join([text, *metadata_values]), branch_patterns()))
    return branches


def detect_candidate_negative_constraints(metadata: dict[str, Any]) -> list[str]:
    negative_keys = semantic_metadata_keys(
        "negative_constraint",
        ("negative_constraints", "not_applicable_when", "excluded_workflow_stages", "excluded_branch_types"),
    )
    return sorted(detect_declared_semantic_values(metadata, negative_keys, (), preserve_unknown=True))


def candidate_policy_type_from_metadata(text: str, metadata: dict[str, Any]) -> str:
    declared = normalize_operational_text(
        " ".join(metadata_terms(metadata, ("policy_type", "branch_type", "unit_type", "retrieval_scope")))
    )
    unit_type = normalize_operational_text(str(metadata.get("unit_type") or ""))
    branches = detect_candidate_branch_types(text, metadata)
    stages = set(detect_candidate_workflow_stages(text, metadata))
    if "document" in declared or unit_type in set(candidate_inference_list("document_context_unit_types")):
        return "document_context"
    if "exception" in declared or unit_type in set(candidate_inference_list("exception_unit_types")):
        return "exception_rule"
    if set(candidate_inference_list("fallback_branch_types")) & branches:
        return "fallback_rule"
    if set(candidate_inference_list("downstream_workflow_stages")) & stages:
        return "downstream_step"
    if unit_type in set(candidate_inference_list("special_policy_unit_types")):
        return unit_type
    return "primary_rule"


def workflow_match_score(facets: PolicyFacets, candidate_stages: list[str]) -> float:
    query_stages = set(facets.workflow_stages)
    candidate = set(candidate_stages)
    if not query_stages:
        return 0.55
    if query_stages & candidate:
        return 1.0
    if candidate & set(facets.negative_workflow_stages):
        return 0.0
    return 0.18 if candidate else 0.35


def condition_entailment_score(facets: PolicyFacets, candidate_conditions: list[str], candidate_stages: list[str]) -> float:
    query_conditions = set(facets.explicit_conditions) | set(facets.scenario_types)
    candidate = set(candidate_conditions)
    if query_conditions and query_conditions <= candidate:
        return 1.0
    if query_conditions & candidate:
        extra = candidate - query_conditions
        return 0.74 if not extra else 0.58
    if candidate & set(facets.negative_workflow_stages):
        return 0.0
    if set(candidate_stages) & set(facets.negative_workflow_stages):
        return 0.12
    return 0.62 if not query_conditions else 0.28


def policy_type_score_for(policy_type: str, metadata: dict[str, Any]) -> float:
    if policy_type == "primary_rule":
        unit_type = normalize_operational_text(str(metadata.get("unit_type") or "policy_rule"))
        return taxonomy_score_map("policy_unit_type_scores").get(unit_type, 0.82)
    return configured_policy_type_scores().get(
        policy_type,
        taxonomy_score_map("policy_unit_type_scores").get(policy_type, 0.4),
    )


def action_alignment_score(facets: PolicyFacets, candidate_channels: list[str], candidate_stages: list[str]) -> float:
    query_channels = set(facets.channel_types)
    candidate = set(candidate_channels)
    required_channels_by_scenario = nested_taxonomy_mapping("action_alignment_rules", "scenario_required_channels")
    required_stage_by_scenario = taxonomy_section("action_alignment_rules").get("scenario_required_workflow_stage")
    required_stage_by_scenario = required_stage_by_scenario if isinstance(required_stage_by_scenario, dict) else {}
    for scenario in facets.scenario_types:
        required_channels = set(required_channels_by_scenario.get(scenario, ()))
        required_stage = str(required_stage_by_scenario.get(scenario) or "")
        if not required_channels:
            continue
        if required_channels <= candidate and (not required_stage or required_stage in candidate_stages):
            return 1.0
        if required_channels <= candidate:
            return 0.55
        if candidate & required_channels:
            return 0.48
        return 0.12
    if query_channels and query_channels <= candidate:
        return 1.0
    if query_channels & candidate:
        return 0.68
    return 0.52 if not query_channels else 0.24


def metadata_terms(metadata: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    output: list[str] = []
    for key in keys:
        output.extend(flatten_metadata_value(metadata.get(key)))
    for container_key in semantic_metadata_containers():
        container = metadata.get(container_key)
        if isinstance(container, dict):
            for key in keys:
                output.extend(flatten_metadata_value(container.get(key)))
        elif isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    for key in keys:
                        output.extend(flatten_metadata_value(item.get(key)))
    return output


def flatten_metadata_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(flatten_metadata_value(item))
        return output
    if isinstance(value, dict):
        output = []
        for item in value.values():
            output.extend(flatten_metadata_value(item))
        return output
    return [str(value)]


def bounded_score(value: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(numeric, 1.0))


def unsupported_scenario_assessment(question: str, results: list[Any]) -> dict[str, Any]:
    scope = build_answer_scope(question)
    facets = build_policy_facets(question, scope)
    if not facets.unsupported_sensitive:
        return {"status": "supported", "reason_codes": [], "confidence": 0.0, "safe_response": ""}

    policy_results = [
        result
        for result in results
        if str((getattr(result, "metadata", {}) or {}).get("chat_source_role") or "") in {"direct_sop", "related_sop", ""}
    ]
    scores = [
        float((getattr(result, "metadata", {}) or {}).get("policy_applicability_score") or 0)
        for result in policy_results
    ]
    top_score = max(scores or [0.0])
    thresholds = applicability_thresholds()
    has_direct_applicable = any(
        float((getattr(result, "metadata", {}) or {}).get("policy_applicability_score") or 0) >= thresholds.get("direct_applicable", 0.58)
        and not ((getattr(result, "metadata", {}) or {}).get("negative_constraint_violations") or [])
        for result in policy_results
    )
    if has_direct_applicable:
        return {"status": "supported", "reason_codes": [], "confidence": round(top_score, 4), "safe_response": ""}

    reason_codes = ["no_direct_applicable_policy"]
    if any((getattr(result, "metadata", {}) or {}).get("negative_constraint_violations") for result in policy_results):
        reason_codes.append("top_chunks_violate_negative_constraints")
    if top_score < thresholds.get("low_unsupported", 0.42):
        reason_codes.append("low_policy_applicability")
    unsupported_rules = taxonomy_section("unsupported_scenario_rules")
    for scenario in facets.scenario_types:
        rule = unsupported_rules.get(scenario)
        if isinstance(rule, dict) and isinstance(rule.get("reason_codes"), list):
            reason_codes.extend(str(reason) for reason in rule["reason_codes"])
        else:
            reason_codes.append(f"no_primary_rule_for:{scenario}")

    primary_scenario = facets.scenario_types[0] if facets.scenario_types else "default"

    return {
        "status": "unsupported_or_ambiguous",
        "scenario_types": list(facets.scenario_types),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "confidence": round(top_score, 4),
        "safe_response": (
            nested_taxonomy_text("unsupported_scenario_messages", primary_scenario)
            or nested_taxonomy_text("unsupported_scenario_messages", "default")
        ),
    }



def prune_answer_to_scope(answer: str, steps: list[str], question: str) -> tuple[str, list[str], list[str]]:
    scope = build_answer_scope(question)
    if not scope.excluded_branch_types:
        return answer, steps, []

    pruned_answer, answer_removed = remove_unasked_segments(answer, scope)
    pruned_steps: list[str] = []
    step_removed: set[str] = set()
    for step in steps:
        branch_terms = detect_pattern_keys(step, branch_patterns()) & set(scope.excluded_branch_types)
        if branch_terms:
            step_removed.update(branch_terms)
            continue
        pruned_steps.append(step)

    removed = sorted(set(answer_removed) | step_removed)
    warnings = [f"out_of_scope_branch_claim_removed:{branch}" for branch in removed]
    return pruned_answer, pruned_steps, warnings


def remove_unasked_segments(answer: str, scope: AnswerScope) -> tuple[str, list[str]]:
    segments = split_answer_segments(answer)
    if len(segments) <= 1:
        branch_terms = detect_pattern_keys(answer, branch_patterns()) & set(scope.excluded_branch_types)
        return answer, sorted(branch_terms)

    kept: list[str] = []
    removed: set[str] = set()
    for segment in segments:
        branch_terms = detect_pattern_keys(segment, branch_patterns()) & set(scope.excluded_branch_types)
        if branch_terms:
            removed.update(branch_terms)
            continue
        kept.append(segment.strip())

    if not kept:
        return answer, sorted(removed)
    return " ".join(kept).strip(), sorted(removed)


def split_answer_segments(answer: str) -> list[str]:
    text = str(answer or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+|;\s+", text)
    output: list[str] = []
    boundary_terms = taxonomy_string_list("answer_segment_boundary_terms")
    boundary_pattern = "|".join(re.escape(term) for term in boundary_terms)
    for part in parts:
        subparts = re.split(rf"(?=\b(?:{boundary_pattern})\b)", part, flags=re.IGNORECASE) if boundary_pattern else [part]
        output.extend(subpart.strip() for subpart in subparts if subpart.strip())
    return output


def detect_pattern_keys(text: str, patterns: PatternMap) -> set[str]:
    normalized = normalize_operational_text(text)
    return {
        key
        for key, values in patterns.items()
        if any(normalize_operational_text(pattern) in normalized for pattern in values)
    }


def detect_declared_semantic_values(
    metadata: dict[str, Any],
    keys: tuple[str, ...],
    allowed_values: Any,
    *,
    preserve_unknown: bool = False,
) -> set[str]:
    canonical_by_normalized = {
        normalize_operational_text(value): str(value)
        for value in allowed_values
        if str(value).strip()
    }
    detected: set[str] = set()
    for value in metadata_terms(metadata, keys):
        normalized_value = normalize_operational_text(value)
        if not normalized_value:
            continue
        if normalized_value in canonical_by_normalized:
            detected.add(canonical_by_normalized[normalized_value])
            continue
        matched = False
        for fragment in re.split(r"[,;|/]+", str(value)):
            normalized_fragment = normalize_operational_text(fragment)
            if normalized_fragment in canonical_by_normalized:
                detected.add(canonical_by_normalized[normalized_fragment])
                matched = True
        for normalized_allowed, canonical in canonical_by_normalized.items():
            if re.search(rf"\b{re.escape(normalized_allowed)}\b", normalized_value):
                detected.add(canonical)
                matched = True
        if preserve_unknown and not matched:
            semantic_id = semantic_value_id(value)
            if semantic_id:
                detected.add(semantic_id)
    return detected


def semantic_value_id(value: Any) -> str:
    return normalize_operational_text(str(value or "")).replace(" ", "_")


def normalize_operational_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", without_accents)).strip()
