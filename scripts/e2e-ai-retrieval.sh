#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8080}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Uploading sample SOP..."
UPLOAD_RESPONSE="$(
  curl -sS \
    -F "file=@${ROOT_DIR}/samples/missing-item-sop.txt" \
    -F "external_id=sop-food-missing-item-upload" \
    -F "title=Uploaded Food Missing Item SOP" \
    -F "status=published" \
    -F 'metadata={"audience":["customer"],"vertical":"food","category":"case_handling","tags":["missing_item","refund"],"case_reasons":["CR_FOOD_MISSING_ITEM"],"owner_team":"CS Ops"}' \
    "${API_BASE_URL}/api/v1/ai/documents/upload"
)"
echo "${UPLOAD_RESPONSE}"

echo
echo "Running hybrid retrieval..."
curl -sS \
  -H "Content-Type: application/json" \
  -d '{"query":"khach khong nhan du mon co duoc refund khong","mode":"hybrid","limit":5,"filters":{"vertical":["food"],"status":["published"]}}' \
  "${API_BASE_URL}/api/v1/ai/retrieve"
echo
