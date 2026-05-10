# CS KB Operator Guide

This guide explains the clean demo flow for local Docker Compose, document curation, publish, and lookup verification.

## 1. Start A Clean Local Stack

Use the explicit project name `kb-mvp` so Docker does not create duplicate projects.

```bash
fish -lc 'docker compose -p kb-mvp up -d --build'
```

If local data must be reset:

```bash
fish -lc 'docker compose -p kb-mvp down -v --remove-orphans'
fish -lc 'docker compose -p kb-mvp up -d --build'
```

If API starts before Postgres is ready, restart API/web after Postgres is ready:

```bash
fish -lc 'docker compose -p kb-mvp up -d api web'
```

Verify:

```bash
fish -lc 'curl -fsS http://localhost:8080/api/v1/homepage | jq "{sops:(.recently_updated|length)}"'
fish -lc 'curl -I --max-time 5 http://localhost:3000'
```

## 2. Configure OpenRouter

Set these values in `.env`:

```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
```

Restart AI/API/web:

```bash
fish -lc 'docker compose -p kb-mvp up -d --build ai api web'
```

Verify the AI container sees the key:

```bash
fish -lc 'docker exec kb-mvp-ai-1 python -c "from app.config import settings; print(bool(settings.openrouter_api_key.strip()), settings.openrouter_model)"'
```

## 3. Upload A Source Document

Open `http://localhost:3000`, then go to `Documents`.

Use `New source` to upload Excel, PDF, DOCX, text, or image files. Uploads are always draft first. Draft content is editable, but it must not be used by production lookup/AI answers until published.

Recommended metadata for CS verification Excel:

```text
Title: Quy định xác minh tài khoản TX, KH
Vertical: account
Audience: customer, driver
Category: verification
Owner team: CS Ops
Tags: account_verification, driver, customer, hotline, chat
Case reasons: CR_ACCOUNT_VERIFICATION
```

Chrome plugin note: if UI file upload is blocked, enable file access for the Codex Chrome Extension at `chrome://extensions` → Codex extension → Details → `Allow access to file URLs`.

## 4. Review Extraction

After upload, select the source document from `Source queue`.

Check:

- `Review` should start as `needs_review`.
- `Version` should start as `draft`.
- `Extraction review` should show extracted units.
- `Indexed chunks` should show raw retrieval chunks for debugging.

For each extraction unit:

- Edit title/content/unit type if extraction is wrong.
- Use `Approve` once the unit is correct.
- `Save changes` only activates when content changes.
- Published versions are read-only by design.

For large Excel files, batch review can be done through API by updating every extraction unit to `approved`, then publishing from UI.

## 5. Publish

In `Documents` → selected document → `Versions`, click:

```text
Publish → Confirm publish
```

Expected result:

- Version status becomes `published`.
- Review status becomes `approved`.
- Extraction units show `read-only published version`.
- Search indexes are synced to Meilisearch and retrieval store.

## 6. Document Lookup Verification

Go to `SOP Lookup` and search for document-specific terms.

Example:

```text
khách hàng hotline xác minh tài khoản cung cấp số điện thoại đặt dịch vụ
```

Expected:

- `Approved document matches` appears.
- Result title/content references `Quy định xác minh tài khoản TX, KH`.
- Result badges include `doc v1`, section/unit type, and `approved`.

## 7. SOP Lookup Verification

Search for a structured SOP term from the seeded SOP repository.

Example:

```text
khách không nhận đủ món refund missing item
```

Expected:

- `Structured SOPs` appears.
- `Xu ly case khach khong nhan du mon` appears.
- SOP detail opens with version, owner, checklist, macros, and governance metadata.

## 8. Retrieval Lab Verification

Go to `Retrieval Lab`.

Example query for Excel document:

```text
hotline xác minh tài khoản khách hàng cung cấp số điện thoại đặt dịch vụ
```

Expected:

- `Evidence` shows chunks from the published Excel document.
- Each result has `Citation: chunk ..., <version_id>`.
- Query expansion shows synonym matches when applicable.

Example query for SOP/document hybrid:

```text
khách không nhận đủ món refund missing item
```

Expected:

- Evidence includes relevant SOP/document chunks.
- Results show lexical/vector rank sources.

## 9. Governance Rules

- Raw uploaded files are not production source of truth.
- Draft extraction is editable but not answerable by agent lookup/AI.
- Publish locks the version.
- To edit a published document, create a new draft version instead of mutating the published version.
- AI extraction suggests structure only. CS Ops/Lead approval decides what becomes searchable.

## 10. Common Troubleshooting

API cannot connect after reset:

```bash
fish -lc 'docker compose -p kb-mvp up -d api web'
```

Check running containers:

```bash
fish -lc 'docker compose -p kb-mvp ps'
```

Check logs:

```bash
fish -lc 'docker compose -p kb-mvp logs --tail=80 api ai postgres'
```

Avoid duplicate Compose projects:

```bash
fish -lc 'docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

If another project owns port `5432`, stop or remove the duplicate project before starting `kb-mvp`.
