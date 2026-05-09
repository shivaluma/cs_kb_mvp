# 03. Data Model

## Core Entities

| Entity | Purpose |
| --- | --- |
| `users` | Authenticated internal users |
| `roles` | Role definitions for RBAC |
| `user_roles` | User-role assignments |
| `sops` | Stable SOP identity and latest published pointer |
| `sop_versions` | Immutable version records |
| `sop_sections` | Structured content by version |
| `categories` | Controlled category taxonomy |
| `tags` | Controlled tag taxonomy and aliases |
| `case_reasons` | CRM case reason mapping |
| `audit_logs` | Important governance actions |
| `search_events` | Search analytics |
| `sop_view_events` | SOP read analytics |
| `ai_events` | AI suggestion, answer, and feedback logs |

## SOP Fields

```json
{
  "id": "uuid",
  "code": "SOP-FOOD-MISSING-ITEM",
  "title": "Xu ly case khach khong nhan du mon",
  "summary": "Huong dan xu ly case thieu/sai mon trong don beFood",
  "audience": ["customer"],
  "vertical": "food",
  "category": "case_handling",
  "tags": ["missing_item", "refund", "merchant", "food"],
  "case_reasons": ["CR_FOOD_MISSING_ITEM"],
  "status": "active",
  "current_version_id": "uuid",
  "owner_team": "CS Ops",
  "updated_at": "2026-05-09T10:00:00Z"
}
```

## Required Sections

| Section | Required | Notes |
| --- | --- | --- |
| `title` | Yes | Process name |
| `summary` | Yes | One to three sentences |
| `when_to_apply` | Yes | Applicability conditions |
| `input_requirements` | Yes | What the agent must verify first |
| `handling_checklist` | Yes | Step-by-step handling |
| `macro_response` | Yes | Copyable customer response |
| `sla` | Optional | SLA when available |
| `escalation` | Optional | Escalation condition |
| `related_sops` | Optional | Internal links |
| `change_history` | Auto | Derived from versions |

## Version Rules

| Rule | Requirement |
| --- | --- |
| Latest published only | Agents only see `sops.current_version_id` |
| Draft isolation | Drafts are excluded from public search and AI index |
| Immutable published version | Published content is not edited directly |
| Archive | Deprecated SOPs are archived, not hard-deleted |
| Rollback | P1: republish a previous version as current |
