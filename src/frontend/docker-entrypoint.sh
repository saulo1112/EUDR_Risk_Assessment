#!/bin/sh
# Regenerate config.js from the API_BASE_URL env var before nginx starts.
# Dropped into /docker-entrypoint.d/ so the stock nginx entrypoint runs it.
# The browser runs on the HOST, so the default points at the host-mapped API
# port (localhost:8000), not the internal docker service name.
set -e
: "${API_BASE_URL:=http://localhost:8000}"

cat > /usr/share/nginx/html/config.js <<EOF
// Generated at container start from API_BASE_URL.
window.API_BASE = "${API_BASE_URL}";
EOF

echo "[frontend] config.js generated: API_BASE=${API_BASE_URL}"
