FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY package.json ./
RUN pnpm install --ignore-scripts
COPY . .
RUN pnpm run build

FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /docker-entrypoint.d/40-cs-kb-env.sh
RUN chmod +x /docker-entrypoint.d/40-cs-kb-env.sh
COPY --from=build /app/dist /usr/share/nginx/html

ENV API_BASE_URL=http://localhost:8080
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/healthz >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
