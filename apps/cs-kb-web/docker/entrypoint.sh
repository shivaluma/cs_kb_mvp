#!/bin/sh
set -eu

cat > /usr/share/nginx/html/env.js <<EOF
window.__CS_KB_CONFIG__ = {
  API_BASE_URL: "${API_BASE_URL:-${VITE_API_BASE_URL:-http://localhost:8080}}"
};
EOF

exec "$@"
