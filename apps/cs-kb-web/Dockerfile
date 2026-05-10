FROM node:22-alpine AS build

WORKDIR /repo
RUN corepack enable
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/cs-kb-web/package.json apps/cs-kb-web/package.json
RUN pnpm install --filter cs-kb-web... --frozen-lockfile --ignore-scripts
COPY apps/cs-kb-web apps/cs-kb-web
WORKDIR /repo/apps/cs-kb-web
RUN pnpm run build

FROM nginx:1.27-alpine AS runtime

COPY apps/cs-kb-web/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/cs-kb-web/docker/entrypoint.sh /docker-entrypoint.d/40-cs-kb-env.sh
RUN chmod +x /docker-entrypoint.d/40-cs-kb-env.sh
COPY --from=build /repo/apps/cs-kb-web/dist /usr/share/nginx/html

ENV API_BASE_URL=http://localhost:8080
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/healthz >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
