You are acting as a senior product designer and frontend engineer.

Your task is to audit and redesign the current SOP Knowledge Base web UI so it feels intuitive, clean, focused, and usable by non-technical CS users.

Context:
This is an internal SOP Knowledge Base for Customer Support.
Users need to:
- search SOPs quickly
- understand which SOP/result is relevant
- open the full SOP
- see the exact matched paragraph/table row highlighted
- use AI chat with grounded citations
- avoid confusion between chunks, documents, categories, collections, and AI answers

Current concern:
The UI may expose too much technical structure, too many irrelevant controls, or too many noisy results.
Users should not feel lost or look inexperienced while using it.
The interface should guide them toward the right action with minimal cognitive load.

Audit goals:
1. Review the current UI flow end-to-end:
   - homepage
   - search input
   - autocomplete/suggestions
   - search results
   - filters
   - SOP detail page
   - highlighted source reference
   - AI chat panel
   - citation/source display
   - empty/loading/error states
   - admin/review states, if present

2. Identify UX problems:
   - unclear primary action
   - noisy layout
   - too many low-value filters
   - confusing terminology
   - chunk-level content shown too prominently
   - AI answer not clearly tied to sources
   - weak visual hierarchy
   - bad empty states
   - missing affordances
   - user has to guess what to do next

3. Redesign the UI around the core user jobs:
   - “Find the right SOP”
   - “Understand why this result is relevant”
   - “Open the full SOP and see the exact matched section”
   - “Ask AI and verify the answer from cited sources”
   - “Escalate or mark uncertainty when SOP guidance conflicts”

Design principles:
- Make search the primary interaction.
- Keep the interface clean and focused.
- Hide advanced controls until needed.
- Prefer progressive disclosure over showing everything at once.
- Show full SOP as the source of truth, not tiny chunks as standalone documents.
- Use clear labels for non-technical CS users.
- Reduce irrelevant metadata in the main UI.
- Keep technical/debug data behind admin/debug mode only.
- Every AI answer must show cited sources clearly.
- Every search result should explain why it matched.
- The UI should make users feel guided, not tested.

Expected UX structure:

Homepage:
- prominent search bar
- clear placeholder examples
- quick shortcuts by category/collection
- recent/pinned/frequently used SOPs
- no overwhelming dashboard widgets

Search input:
- debounce search-as-you-type
- do not search 1-character queries
- show autocomplete suggestions separately from full search
- suggestions may include SOP title, macro, section, or popular query

Search results:
Each result card should include:
- result title
- SOP document title
- section path
- short matched snippet
- badges only if useful: Risk, Channel, Audience, Updated
- reason/match hint, e.g. “Matched forbidden phrase” or “Matched email macro”
- primary action: “Open in SOP”
- optional action: “Ask AI about this”

Do not show:
- raw chunk IDs
- internal score
- embedding/vector details
- excessive metadata
- long technical labels
unless debug mode is enabled.

SOP detail page:
- full SOP content is the main view
- table/paragraph/list formatting must be readable
- matched source reference should be highlighted
- page should auto-scroll to highlighted block when opened from search
- right sidebar may show:
  - table of contents
  - related SOPs
  - source/citation metadata
  - AI question box
- avoid making the user read isolated chunks without context

AI chat:
- AI answer should be visually separate from SOP source
- answer must include citations
- citations should open the exact source block in the full SOP
- if multiple SOPs are used, group sources by:
  - primary source
  - secondary/reference source
  - internal-only/background source
- if conflict is detected, show a clear warning:
  “SOP guidance may conflict. Please review with owner/QA.”
- AI must not hide uncertainty

Filters:
- default filters should be minimal:
  - Category
  - Audience
  - Channel/Vertical
  - Updated/Current
- advanced filters should be collapsible:
  - risk level
  - document type
  - source type
  - owner team
  - status
- admin-only filters should not appear to normal CS users

Admin/review mode:
- separate from CS portal mode
- can show review status, chunk quality, source ref quality, indexing status, debug scores
- should not pollute normal CS workflow

Deliverables:
1. UX audit summary
2. Main user journeys
3. Problems found, grouped by severity
4. Proposed information architecture
5. Redesigned page-level flow
6. Component-level recommendations
7. Copy/label improvements
8. Empty/loading/error state improvements
9. Accessibility and responsiveness notes
10. Before/after explanation
11. Implementation checklist
12. Frontend files/components to modify
13. Any backend/API contract changes needed

Implementation expectations:
- Make practical changes in the existing codebase where possible.
- Do not rewrite the whole app unless necessary.
- Prefer small, high-impact UI improvements.
- Keep existing business logic intact.
- Preserve source_refs, document_id, chunk_id, and highlight behavior.
- Do not remove admin/debug capabilities, but hide them from normal users.
- Use existing design system/components if available.
- Ensure responsive behavior for common laptop screen sizes.

Acceptance criteria:
- A CS user can search and open the right SOP without understanding chunks or embeddings.
- Search results clearly show what matched and where.
- Clicking a result opens the full SOP and highlights the exact source.
- AI answers are grounded with citations.
- Irrelevant metadata is hidden from normal users.
- Filters are useful but not overwhelming.
- UI has clear hierarchy and fewer distractions.
- Empty/loading/error states guide the user.
- Admin/debug information is separated from normal user experience.
