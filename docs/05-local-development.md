# 05. Local Development

## Full Stack

```sh
cp .env.example .env
docker compose up --build
```

## Web

```sh
cd apps/cs-kb-web
pnpm install
pnpm run dev
```

The Vite dev server runs on `http://localhost:3000`.
The frontend uses shadcn/ui v4 components and Tailwind CSS v4 tokens.

## API

`make api` loads root `.env` and optional `.env.local`. Use `.env.local` for
non-Docker host overrides so local processes do not try to call Docker DNS names
such as `ai`, `postgres`, or `meilisearch`.

```sh
cp .env.local.example .env.local
```

For local processes with cloud infra, set at minimum:

```env
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DB?sslmode=require
DATABASE_CONNECT_TIMEOUT_SECONDS=5
AI_BASE_URL=http://localhost:8090
MEILI_HOST=http://localhost:7700
QDRANT_URL=https://YOUR_QDRANT_HOST
QDRANT_API_KEY=YOUR_QDRANT_API_KEY
```

`DATABASE_CONNECT_TIMEOUT_SECONDS` makes API startup fail fast when cloud
Postgres is blocked, down, or unreachable. Without a reachable DB, `make api`
should crash with a clear `connect to postgres` error instead of hanging.

If Meilisearch is also hosted remotely, set `MEILI_HOST` and
`MEILI_MASTER_KEY` to the cloud values.

```sh
make api
```

The Go API defaults to `http://localhost:8080`.

## AI

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make ai
```

Or let Makefile create/install the local AI virtualenv:

```sh
make setup-ai
make ai
```

`make setup-ai` requires Python 3.12+. It uses `python3.12` when available, then
falls back to the bundled Codex Python 3.12 runtime. To force a specific Python:

```sh
make setup-ai PYTHON=/path/to/python3.12
```

## Fish Shell Notes

The preferred command wrapper for this workspace is:

```sh
fish -lc '<command>'
```

## Verification

```sh
cd apps/cs-kb-api
go test ./...
```

```sh
cd apps/cs-kb-ai
python3 -m compileall app
```

```sh
cd apps/cs-kb-web
pnpm run build
```
