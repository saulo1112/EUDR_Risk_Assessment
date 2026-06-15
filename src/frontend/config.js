// Runtime configuration for the frontend.
// In Docker this file is regenerated at container start from the
// API_BASE_URL env var (see src/frontend/docker-entrypoint.sh). The value
// below is the default used for local development (python -m http.server).
window.API_BASE = "http://localhost:8000";
