FROM node:22-alpine

WORKDIR /repo
RUN corepack enable
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/cs-kb-web/package.json apps/cs-kb-web/package.json
RUN pnpm install --filter cs-kb-web... --frozen-lockfile
COPY apps/cs-kb-web apps/cs-kb-web

WORKDIR /repo/apps/cs-kb-web

EXPOSE 3000
CMD ["pnpm", "run", "dev"]
