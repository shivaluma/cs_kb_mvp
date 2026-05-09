# 04. API Contracts

This is the short API summary. The fuller endpoint contract lives in `04-api-contract.md`.

## Go API

- `GET /healthz`
- `GET /api/v1/homepage`
- `GET /api/v1/sops`
- `GET /api/v1/sops/:id`
- `POST /api/v1/search`
- `POST /api/v1/ai/suggest`
- Analytics endpoints are planned after event persistence is wired.

## Python AI service

- `GET /healthz`
- `POST /ai/v1/search/semantic`
- `POST /ai/v1/suggest`
- `POST /ai/v1/index/sop-version`

## Contract expectations

- AI responses always include `citations`
- Search responses separate result list and applied filters
- Publish flow should return indexing job status in a later iteration
