# 07. AI Guidelines

## Scope

AI is an assistant for retrieval and summarization over approved SOP content. It must not create new policy or make final compensation/refund decisions.

## Allowed

- Summarize published SOP sections.
- Suggest related SOPs.
- Extract handling checklist.
- Recommend existing approved macro responses.
- Draft responses only when grounded in approved macro content.
- Return citations with `sop_id`, `version_id`, and `section`.

## Not Allowed

- Create refund policy.
- Decide compensation.
- Use draft or archived SOPs.
- Answer without source.
- State that a case is definitely eligible unless the cited SOP explicitly says so.

## Response Shape

```json
{
  "answer": "Case nay nen kiem tra SOP Sai/Thieu mon...",
  "suggested_sops": [
    {
      "sop_id": "uuid",
      "title": "Xu ly khach khong nhan du mon",
      "version": 3,
      "confidence": 0.91
    }
  ],
  "citations": [
    {
      "sop_id": "uuid",
      "version_id": "uuid",
      "section": "handling_checklist"
    }
  ],
  "warnings": []
}
```

## Guardrail Rules

| Rule | Behavior |
| --- | --- |
| No citation | Return safe fallback |
| Low confidence | Suggest search refinements and candidate SOPs only |
| Draft/archived source | Exclude from retrieval |
| Policy-sensitive answer | Cite exact section and avoid definitive language |
| AI service down | API keeps keyword SOP search/read working |
