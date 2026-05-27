# CS SOP KB UI Redesign Audit

## Executive Summary

The UI is now oriented around the CS agent job: search a published SOP, understand why a result matched, open the SOP context, and verify AI answers from cited sources. Technical retrieval details remain available in admin/debug surfaces, but the normal CS path no longer foregrounds chunk IDs, raw scores, model names, or retrieval traces.

## Main User Journeys

1. Portal home: user searches from a prominent SOP search box, uses suggestions after two characters, or opens pinned/recent/category shortcuts.
2. Lookup: user runs a guarded search, sees best SOP evidence first, opens highlighted source context, and can still browse SOP document matches.
3. SOP detail: user reads the published SOP as the source of truth, uses table-of-contents navigation, copies approved macros, and sees governance notes without raw IDs by default.
4. SOP chat: user asks a question, sees a grounded answer, citation count, source groups, and review warnings. Debug traces are hidden unless debug mode is enabled.
5. Admin/review: CS Ops can still inspect chunks, extraction quality, retrieval lab scores, indexing status, and relation governance.

## Problems Found

### High Severity

- Chrome audit on `2026-05-23` showed the portal browse feed returning empty while search shortcuts and retrieval-backed flows still worked. The old empty state implied there was no content at all, which could send CS users away from the system even when approved evidence is searchable.
- Lookup could stay in `Searching…` with skeleton rows for more than 10 seconds. Without a slow-search recovery path, users could not tell whether to retry, shorten the query, or switch to grounded chat.
- Chat answers used a narrow center column inside a wide desktop viewport, while warning/debug chips took more visual weight than the answer. This made the correct answer feel less trustworthy and harder to scan.
- Empty admin workspaces such as Tools and Case Assist showed blank panels or blank tables without examples, recovery actions, or next steps.
- Raw retrieval scores appeared on normal source cards, which made CS users interpret backend ranking as policy confidence.
- Chat exposed context candidates, model route, model name, latency, and retrieval debug in the normal answer view.
- Search filters prioritized collection/content type before more familiar CS facets such as audience, category, and channel.
- SOP detail exposed version IDs and current version pointers in the default reading path.

### Medium Severity

- Search had backend one-character protection, but the search bar did not clearly guide users before submit.
- Autocomplete existed in the API but was not wired into the main search fields.
- Source labels used technical wording such as source context/source unavailable instead of SOP/source verification language.
- Empty states sometimes spoke to system operators instead of CS users.

### Low Severity

- Some admin pages intentionally remain dense. This is acceptable because they serve CS Ops and QA rather than normal portal users.
- Case Assist showed raw match score. It now shows source role by default and keeps score in debug mode.

## Proposed Information Architecture

- CS workspace: Portal, Lookup, Chat, Case Assist.
- Knowledge library: Collections and Tools.
- Review and governance: Ops console, Upload, Source queue, Documents, Feedback, Relations.
- Admin debug: Synonyms and Retrieval lab.

## Redesigned Page Flow

- Portal leads with search and shortcuts, not dashboard widgets.
- Lookup separates best SOP evidence from SOP document matches.
- Source cards show human labels, section/title, snippet/highlight, citations, and an "Open in SOP" action.
- SOP detail keeps the full published SOP as the reading surface and moves technical identifiers to debug mode.
- Chat shows sources used, citations, and warning language suitable for review/escalation.

## Component Recommendations Implemented

- `SearchBar`: min length guard, autocomplete dropdown, suggestion selection hook.
- `FilterGrid`: primary filters are Audience, Category, Channel/vertical. Advanced filters contain Collection, Content type, and Task type.
- `SourceContextCard`: raw scores and console source diagnostics are debug-only; source labels are SOP-focused.
- `ChatWorkspace`: retrieval trace, model route, model name, and latency are debug-only.
- `SOPDetailWorkspace`: table of contents added; raw version IDs hidden by default.
- `EmptyPanel`: now supports scoped actions so empty states can offer the next useful operation instead of only explanatory text.
- `PortalWorkspace`: distinguishes an unavailable browse feed from an actually empty knowledge base and gives direct search/chat actions.
- `LookupWorkspace`: adds a slow-search recovery panel with retry and chat fallback.
- `CaseAssistWorkspace`: adds example issue chips and clearer action-card guidance before a result is selected.
- `ToolsWorkspace`: replaces blank empty tables with an action-oriented empty state and a clear-filter affordance.

## Copy And Labels

- "Context candidates" became "Sources used".
- "Open source" became "Open in SOP".
- "Source unavailable" became "Needs source check".
- Empty search state now suggests SOP title, case reason, macro name, or shorter wording.
- Chat warnings map internal warning tokens to review-oriented language.

## Empty, Loading, Error States

- Empty lookup now teaches what to search for.
- No-results state tells CS users how to recover and when to send feedback.
- Chat keeps uncertainty visible and separates review warnings from grounded answers.
- Slow lookup now stops being an indefinite skeleton-only state and gives retry/chat alternatives.
- Empty portal state now says "Published list unavailable" when the browse API is empty but evidence search remains available.
- Empty Case Assist and Tools states now expose concrete examples or filter recovery actions.

## Screenshot Audit Evidence

Screenshots were captured through Chrome against the local web app using the deployed API and saved under `.tmp/ui-audit-20260523/`.

- `portal.png`: large blank browse state said no SOPs existed while quick search prompts remained available.
- `lookup.png`: route stayed in loading state, leaving source detail blank and no recovery action.
- `chat-session.png`: warning/debug chips dominated the answer area and the answer column was too narrow for the available viewport.
- `case-assist.png`: empty query state required users to invent the first query without operational examples.
- `tools.png`: empty result table showed an empty grid instead of a decision point.

## Accessibility And Responsiveness

- Search suggestions are keyboard focusable buttons.
- Existing focus rings and skip link are preserved.
- Filters remain collapsible and responsive.
- SOP detail navigation uses native buttons and scroll targets.
- Debug-only content is not needed for normal task completion.

## Backend/API Contract Changes

- No new backend contract was required.
- Existing `/api/v1/search/autocomplete` is now used by Portal and Lookup.
- Existing `debug` conventions are respected client-side through `?debug=1` or `localStorage.cs-kb-debug=1`.

## Implementation Checklist

- [x] Hide raw retrieval score from normal CS source cards.
- [x] Hide chat debug/model metadata from normal CS users.
- [x] Wire autocomplete to Portal and Lookup.
- [x] Enforce two-character search affordance in the search component.
- [x] Simplify default filters.
- [x] Keep advanced filters available.
- [x] Keep admin/debug workflows intact.
- [x] Preserve source refs, document IDs, chunk IDs, and highlight behavior.
- [x] Add SOP detail table of contents.
- [x] Keep Retrieval lab score/debug visibility for admins.
