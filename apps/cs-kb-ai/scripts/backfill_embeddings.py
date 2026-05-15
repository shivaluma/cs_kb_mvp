#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import repository  # noqa: E402
from app.config import settings  # noqa: E402
from app.embedding import (  # noqa: E402
    embed_texts,
    embedding_runtime_metadata,
    remote_embedding_configured,
    vector_literal,
)
from app.search_labels import embedding_text_for_unit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ai_chunks embeddings into a new pgvector dimension.")
    parser.add_argument("--batch-size", type=int, default=64, help="Chunks to embed per batch")
    parser.add_argument("--limit", type=int, default=0, help="Maximum chunks to backfill in this run; 0 means all")
    parser.add_argument("--swap", action="store_true", help="Swap embedding_new into embedding after backfill is complete")
    parser.add_argument("--allow-local", action="store_true", help="Allow local_hash embeddings for dev/test backfills")
    parser.add_argument("--dry-run", action="store_true", help="Print pending counts without writing")
    args = parser.parse_args()

    if settings.embedding_dimensions <= 0:
        print("EMBEDDING_DIMENSIONS must be positive", file=sys.stderr)
        return 1
    if not remote_embedding_configured() and not args.allow_local:
        print(
            "Remote embedding provider is not configured. Set OPENROUTER_API_KEY/EMBEDDING_API_KEY "
            "or pass --allow-local for dev/test only.",
            file=sys.stderr,
        )
        return 1

    with repository.connection() as conn:
        conn.row_factory = dict_row
        ensure_embedding_new_column(conn, args.dry_run)
        pending = pending_count(conn)
        print(f"pending_chunks={pending} embedding_dimensions={settings.embedding_dimensions}")
        if args.dry_run:
            return 0

        processed = backfill_batches(conn, args.batch_size, args.limit)
        print(f"processed_chunks={processed}")

        if args.swap:
            remaining = pending_count(conn)
            if remaining:
                print(f"cannot_swap_pending_chunks={remaining}", file=sys.stderr)
                return 1
            swap_embedding_columns(conn)
            print("swapped_embedding_new_into_embedding=true")

    return 0


def ensure_embedding_new_column(conn: Any, dry_run: bool) -> None:
    if dry_run:
        return
    conn.execute(f"ALTER TABLE ai_chunks ADD COLUMN IF NOT EXISTS embedding_new vector({settings.embedding_dimensions})")


def pending_count(conn: Any) -> int:
    if not embedding_new_column_exists(conn):
        return int(conn.execute("SELECT COUNT(*) AS count FROM ai_chunks").fetchone()["count"])
    return int(conn.execute("SELECT COUNT(*) AS count FROM ai_chunks WHERE embedding_new IS NULL").fetchone()["count"])


def embedding_new_column_exists(conn: Any) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = 'ai_chunks'
            AND column_name = 'embedding_new'
        ) AS exists
        """
    ).fetchone()
    return bool(row["exists"])


def fetch_batch(conn: Any, batch_size: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id::text AS chunk_id,
               section,
               heading,
               content,
               metadata
        FROM ai_chunks
        WHERE embedding_new IS NULL
        ORDER BY created_at, id
        LIMIT %s
        """,
        (batch_size,),
    ).fetchall()
    return [dict(row) for row in rows]


def backfill_batches(conn: Any, batch_size: int, limit: int) -> int:
    processed = 0
    while True:
        remaining_limit = limit - processed if limit > 0 else batch_size
        if limit > 0 and remaining_limit <= 0:
            return processed
        rows = fetch_batch(conn, min(batch_size, remaining_limit))
        if not rows:
            return processed

        texts = [embedding_input(row) for row in rows]
        embeddings = embed_texts(texts)
        runtime_metadata = embedding_runtime_metadata()
        update_rows = [
            (
                vector_literal(embeddings[index]),
                json.dumps(runtime_metadata),
                row["chunk_id"],
            )
            for index, row in enumerate(rows)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE ai_chunks
                SET embedding_new = %s::vector,
                    metadata = metadata || %s::jsonb
                WHERE id = %s
                """,
                update_rows,
            )
        processed += len(rows)
        print(f"processed_chunks={processed}")


def embedding_input(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    unit_type = str(metadata.get("unit_type") or row.get("section") or "")
    return embedding_text_for_unit(row.get("heading") or "", row.get("content") or "", unit_type)


def swap_embedding_columns(conn: Any) -> None:
    with conn.transaction():
        conn.execute("DROP INDEX IF EXISTS idx_ai_chunks_embedding_hnsw")
        conn.execute("ALTER TABLE ai_chunks DROP COLUMN embedding")
        conn.execute("ALTER TABLE ai_chunks RENAME COLUMN embedding_new TO embedding")
        conn.execute("ALTER TABLE ai_chunks ALTER COLUMN embedding SET NOT NULL")
        conn.execute("CREATE INDEX idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops)")


if __name__ == "__main__":
    raise SystemExit(main())
