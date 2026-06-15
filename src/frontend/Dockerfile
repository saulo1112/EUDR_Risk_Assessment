# EUDR Risk dashboard — static files served by nginx.
# Build context is the repo root (see docker/docker-compose.yml).
FROM nginx:alpine

# Static assets only (not the Dockerfile / entrypoint).
COPY src/frontend/index.html \
     src/frontend/style.css \
     src/frontend/app.js \
     src/frontend/config.js \
     /usr/share/nginx/html/

# config.js is regenerated from API_BASE_URL at startup by the stock nginx
# entrypoint, which runs executable *.sh files in /docker-entrypoint.d/.
COPY src/frontend/docker-entrypoint.sh /docker-entrypoint.d/40-config-js.sh
RUN chmod +x /docker-entrypoint.d/40-config-js.sh

EXPOSE 80
