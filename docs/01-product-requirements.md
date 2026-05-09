# 01. Product Requirements

## Problem

CS currently searches SOPs across Excel/email, which makes it hard to find the latest approved policy, slows handling time, increases cognitive load, and creates risk of using the wrong SOP version.

## Goals

| Goal | Description |
| --- | --- |
| Faster SOP lookup | CS can find relevant SOPs during live case handling |
| Single source of truth | Agents see only the latest published version |
| Version governance | Draft, review, publish, archive, and version history |
| Searchable knowledge | Search by keyword, tag, category, audience, vertical, and case reason |
| Usage analytics | Track usage, failed searches, no-click searches, and adoption |
| AI-ready foundation | Approved, structured SOP data supports future AI assistant |

## Non-goals

| Non-goal | Reason |
| --- | --- |
| AI deciding refund or compensation | High policy and compliance risk |
| External chatbot for customers or drivers | Requires stronger governance and audit |
| Full CRM automation | MVP only needs basic links/context |
| Realtime sync from every source | Batch Excel migration is enough for MVP |
| Complex workflow engine | Draft/review/publish is sufficient initially |

## P0 User Stories

| ID | Story |
| --- | --- |
| US-001 | Agent searches by natural keywords |
| US-002 | Agent sees title, snippet, category, tags, and updated date in results |
| US-003 | Agent filters by audience, category, product/vertical, and case reason |
| US-006 | Agent reads SOP in a standard structure |
| US-007 | Agent copies macro response |
| US-008 | Agent sees handling checklist |
| US-009 | Agent sees SLA, escalation condition, and related SOPs |
| US-010 | Agent sees last update and version |
| US-011 | SOP Admin creates a draft version |
| US-012 | Lead reviews and publishes a version |
| US-013 | Agent sees only latest published version |
| US-014 | Admin sees version history |
| US-019 | AI answer must cite source SOP/version |
| US-020 | AI suggestions and feedback are logged |
| US-021 | Lead sees most accessed SOPs |
| US-022 | Lead sees zero-result queries |
| US-024 | Lead sees weekly adoption |

## Acceptance Criteria

| Area | Criteria |
| --- | --- |
| Search | Query `khong nhan du mon` returns relevant missing-item/refund/escalation SOPs with metadata |
| Version control | Draft v4 and published v3 can coexist; agents only see v3 |
| Publish | Publishing v4 updates `current_version_id` and triggers re-indexing |
| Archive | Archived SOPs are hidden from normal agent search but visible to lead/admin in audit mode |
| Analytics | Search, click, result count, role, and latency are recorded |
| AI | Any AI answer includes SOP citation; low-confidence cases return a safe fallback |
