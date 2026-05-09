#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8080}"

echo "Current active synonym groups..."
curl -sS "${API_BASE_URL}/api/v1/search/synonyms?status=active" | jq 'map({canonical_key, synonym_type, term_count: (.terms | length)})'

echo
echo "Creating a draft synonym group..."
CREATE_RESPONSE="$(
  curl -sS \
    -H "Content-Type: application/json" \
    -d '{"canonical_key":"refund_delay","synonym_type":"one_way","domain":"payment","audience":"customer","status":"draft","created_by":"cs-ops-demo","terms":["tien chua ve vi","chua nhan tien refund"]}' \
    "${API_BASE_URL}/api/v1/search/synonyms"
)"
echo "${CREATE_RESPONSE}" | jq '{id, canonical_key, status, terms}'
GROUP_ID="$(echo "${CREATE_RESPONSE}" | jq -r '.id')"

echo
echo "Submitting and approving the synonym group..."
curl -sS \
  -H "Content-Type: application/json" \
  -d '{"actor":"cs-ops-demo"}' \
  "${API_BASE_URL}/api/v1/search/synonyms/${GROUP_ID}/submit-review" | jq '{id, canonical_key, status}'
curl -sS \
  -H "Content-Type: application/json" \
  -d '{"actor":"cs-lead-demo"}' \
  "${API_BASE_URL}/api/v1/search/synonyms/${GROUP_ID}/approve" | jq '{id, canonical_key, status, approved_by}'

echo
echo "Verifying runtime query expansion..."
curl -sS \
  -H "Content-Type: application/json" \
  -d '{"query":"chua nhan tien refund"}' \
  "${API_BASE_URL}/api/v1/ai/retrieve" | jq '{normalized_query, query_expansion, warnings}'

echo
echo "Syncing active synonyms to Meilisearch settings..."
curl -sS -X POST "${API_BASE_URL}/api/v1/search/synonyms/sync" | jq '{synonym_count, indexes}'
