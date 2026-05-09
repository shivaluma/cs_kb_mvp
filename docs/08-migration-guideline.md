# 08. Migration Guideline

## Source Audit

Capture these fields from each Excel/email SOP source:

- Existing title.
- Owner/team.
- Audience.
- Vertical.
- Case reason.
- Applicability condition.
- Required inputs.
- Handling steps.
- Macro/script.
- SLA.
- Escalation rule.
- Related policy or SOP.
- Last updated date.

## Mapping

| Source Field | Target Field |
| --- | --- |
| SOP name | `sops.title` |
| Short description | `sops.summary` |
| Team owner | `sops.owner_team` |
| Product | `sops.vertical` |
| Customer/driver/merchant | `sops.audience` |
| Case reason | `case_reasons.code` |
| Process steps | `sop_sections.handling_checklist` |
| Macro | `sop_sections.macro_response` |
| Updated note | `sop_versions.change_summary` |

## Import Validation

Reject or flag rows when:

- Required sections are missing.
- Tag is not in controlled taxonomy.
- Case reason is unknown.
- Owner team is empty.
- Published SOP has no effective date.

## Pilot Recommendation

Start with a high-volume category such as food missing item/refund because search value and policy risk are both visible there.
