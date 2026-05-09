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

```sh
cd apps/cs-kb-api
go run ./cmd/api
```

The Go API defaults to `http://localhost:8080`.

## AI

```sh
cd apps/cs-kb-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
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
