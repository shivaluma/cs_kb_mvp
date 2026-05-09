from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from psycopg import Connection
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import ConnectionPool

from app.config import settings
from app.embedding import vector_literal
from app.schemas import DocumentMetadata, RetrievalFilters, SynonymGroupCreateRequest, SynonymSuggestionAcceptRequest
from app.text_processing import normalize_phrase, tokenize


pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
_synonym_cache: tuple[float, list[dict[str, Any]]] = (0, [])
SYNONYM_CACHE_SECONDS = 30


@contextmanager
def connection() -> Iterator[Connection[Any]]:
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        conn.row_factory = tuple_row
        yield conn


def ensure_schema() -> None:
    with connection() as conn:
        conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        conn.execute(
            """
            CREATE OR REPLACE FUNCTION immutable_unaccent(text)
            RETURNS text
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
            STRICT
            AS $$
              SELECT unaccent('public.unaccent', $1)
            $$;
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_documents (
              id uuid PRIMARY KEY,
              external_id text NOT NULL UNIQUE,
              title text NOT NULL,
              source_filename text NOT NULL,
              content_type text NOT NULL,
              status text NOT NULL DEFAULT 'active',
              current_version_id uuid,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_document_versions (
              id uuid PRIMARY KEY,
              document_id uuid NOT NULL REFERENCES ai_documents(id),
              version_number integer NOT NULL,
              status text NOT NULL DEFAULT 'draft',
              checksum text NOT NULL,
              change_summary text NOT NULL DEFAULT '',
              raw_text text NOT NULL,
              chunk_count integer NOT NULL DEFAULT 0,
              created_by text NOT NULL DEFAULT 'system',
              approved_by text,
              effective_from timestamptz,
              published_at timestamptz,
              archived_at timestamptz,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE (document_id, version_number)
            )
            """
        )
        conn.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ai_documents_current_version_fk'
              ) THEN
                ALTER TABLE ai_documents
                ADD CONSTRAINT ai_documents_current_version_fk
                FOREIGN KEY (current_version_id) REFERENCES ai_document_versions(id);
              END IF;
            END
            $$;
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS ai_chunks (
              id uuid PRIMARY KEY,
              document_id uuid NOT NULL REFERENCES ai_documents(id),
              version_id uuid NOT NULL REFERENCES ai_document_versions(id),
              chunk_index integer NOT NULL,
              section text NOT NULL DEFAULT 'body',
              heading text NOT NULL DEFAULT '',
              content text NOT NULL,
              token_count integer NOT NULL DEFAULT 0,
              embedding vector({settings.embedding_dimensions}) NOT NULL,
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE (version_id, chunk_index)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_retrieval_events (
              id uuid PRIMARY KEY,
              query text NOT NULL,
              filters jsonb NOT NULL DEFAULT '{}'::jsonb,
              mode text NOT NULL,
              result_count integer NOT NULL,
              latency_ms integer NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_audit_events (
              id uuid PRIMARY KEY,
              actor text NOT NULL DEFAULT 'system',
              action text NOT NULL,
              entity_type text NOT NULL,
              entity_id uuid NOT NULL,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_documents_status ON ai_documents(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_versions_status ON ai_document_versions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_document_version ON ai_chunks(document_id, version_id)")
        conn.execute("DROP INDEX IF EXISTS idx_ai_chunks_content_fts")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_content_unaccent_fts ON ai_chunks USING gin (to_tsvector('simple', immutable_unaccent(content)))")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_metadata ON ai_chunks USING gin (metadata)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops)"
        )
        ensure_search_taxonomy_schema(conn)
        seed_search_taxonomy(conn)


def ensure_search_taxonomy_schema(conn: Connection[Any]) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS taxonomy_intents (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          intent_key text NOT NULL UNIQUE,
          domain text NOT NULL DEFAULT '',
          audience text NOT NULL DEFAULT '',
          related_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
          risk_level text NOT NULL DEFAULT 'medium',
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_synonym_groups (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          canonical_key text NOT NULL,
          synonym_type text NOT NULL,
          domain text NOT NULL DEFAULT '',
          audience text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          created_by text NOT NULL DEFAULT 'system',
          approved_by text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_synonym_terms (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          group_id uuid NOT NULL REFERENCES search_synonym_groups(id) ON DELETE CASCADE,
          term text NOT NULL,
          normalized_term text NOT NULL,
          language text NOT NULL DEFAULT 'vi',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (group_id, normalized_term)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_synonym_suggestions (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          canonical_key text NOT NULL DEFAULT '',
          suggested_terms jsonb NOT NULL DEFAULT '[]'::jsonb,
          source text NOT NULL DEFAULT 'analytics',
          confidence numeric NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'pending',
          evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_intents_status ON taxonomy_intents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_synonym_groups_status ON search_synonym_groups(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_synonym_groups_canonical ON search_synonym_groups(canonical_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_synonym_terms_normalized ON search_synonym_terms(normalized_term)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_synonym_suggestions_status ON search_synonym_suggestions(status)")


def seed_search_taxonomy(conn: Connection[Any]) -> None:
    cleanup_synonym_normalized_terms(conn)
    intents = [
        ("missing_item", "food", "customer", ["refund", "merchant", "order_issue"], "medium"),
        ("wrong_item", "food", "customer", ["refund", "merchant", "order_issue"], "medium"),
        ("refund", "payment", "customer", ["compensation", "payment"], "high"),
        ("cancel_trip", "ride-hailing", "customer", ["cancellation", "trip"], "medium"),
    ]
    for intent_key, domain, audience, related_tags, risk_level in intents:
        conn.execute(
            """
            INSERT INTO taxonomy_intents (intent_key, domain, audience, related_tags, risk_level, status)
            VALUES (%s, %s, %s, %s::jsonb, %s, 'active')
            ON CONFLICT (intent_key) DO NOTHING
            """,
            (intent_key, domain, audience, json.dumps(related_tags), risk_level),
        )

    seed_groups = [
        ("missing_item", "one_way", "food", "customer", ["thiếu món", "không nhận đủ món", "khach khong nhan du mon", "thiếu topping", "giao thiếu nước", "missing item"]),
        ("wrong_item", "one_way", "food", "customer", ["sai món", "giao sai combo", "wrong item"]),
        ("refund", "regular", "payment", "customer", ["hoàn tiền", "bồi hoàn", "cashback", "refund"]),
        ("cancel_trip", "one_way", "ride-hailing", "customer", ["hủy cuốc", "huy cuoc", "cancel ride"]),
    ]
    for canonical_key, synonym_type, domain, audience, terms in seed_groups:
        group_row = conn.execute(
            """
            SELECT id FROM search_synonym_groups
            WHERE canonical_key = %s AND synonym_type = %s AND status <> 'archived'
            LIMIT 1
            """,
            (canonical_key, synonym_type),
        ).fetchone()
        if group_row:
            group_id = str(group_row[0])
        else:
            group_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO search_synonym_groups (
                  id, canonical_key, synonym_type, domain, audience, status, created_by, approved_by
                )
                VALUES (%s, %s, %s, %s, %s, 'active', 'seed', 'seed')
                """,
                (group_id, canonical_key, synonym_type, domain, audience),
            )
        upsert_synonym_terms_tx(conn, group_id, terms)
    cleanup_synonym_normalized_terms(conn)


def cleanup_synonym_normalized_terms(conn: Connection[Any]) -> None:
    rows = conn.execute("SELECT id::text, group_id::text, term FROM search_synonym_terms").fetchall()
    keep_by_key: dict[tuple[str, str], str] = {}
    delete_ids: list[str] = []
    updates: list[tuple[str, str]] = []
    for row in rows:
        term_id, group_id, term = str(row[0]), str(row[1]), str(row[2])
        normalized = normalize_phrase(term)
        if not normalized:
            delete_ids.append(term_id)
            continue
        key = (group_id, normalized)
        if key in keep_by_key:
            delete_ids.append(term_id)
            continue
        keep_by_key[key] = term_id
        updates.append((normalized, term_id))

    if delete_ids:
        conn.execute("DELETE FROM search_synonym_terms WHERE id = ANY(%s)", (delete_ids,))
    for normalized, term_id in updates:
        conn.execute(
            "UPDATE search_synonym_terms SET normalized_term = %s WHERE id = %s",
            (normalized, term_id),
        )


def create_document_version(
    *,
    external_id: str,
    title: str,
    source_filename: str,
    content_type: str,
    checksum: str,
    raw_text: str,
    chunks: list[dict[str, Any]],
    metadata: DocumentMetadata,
    status: str,
    created_by: str,
    change_summary: str,
) -> dict[str, Any]:
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    metadata_json = json.dumps(metadata.model_dump())

    with connection() as conn:
        with conn.transaction():
            existing = conn.execute(
                "SELECT id FROM ai_documents WHERE external_id = %s",
                (external_id,),
                prepare=False,
            ).fetchone()
            if existing:
                document_id = str(existing[0])
                conn.execute(
                    """
                    UPDATE ai_documents
                    SET title = %s,
                        source_filename = %s,
                        content_type = %s,
                        metadata = %s::jsonb,
                        status = 'active',
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (title, source_filename, content_type, metadata_json, document_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ai_documents (
                      id, external_id, title, source_filename, content_type, status, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active', %s::jsonb)
                    """,
                    (document_id, external_id, title, source_filename, content_type, metadata_json),
                )

            next_version = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM ai_document_versions WHERE document_id = %s",
                (document_id,),
            ).fetchone()[0]

            conn.execute(
                """
                INSERT INTO ai_document_versions (
                  id, document_id, version_number, status, checksum, change_summary, raw_text,
                  chunk_count, created_by, approved_by, effective_from, published_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), CASE WHEN %s = 'published' THEN now() ELSE NULL END)
                """,
                (
                    version_id,
                    document_id,
                    next_version,
                    status,
                    checksum,
                    change_summary,
                    raw_text,
                    len(chunks),
                    created_by,
                    created_by if status == "published" else None,
                    status,
                ),
            )

            insert_chunks(conn, document_id, version_id, chunks)

            if status == "published":
                publish_version_tx(conn, version_id, created_by)

            audit_tx(
                conn,
                actor=created_by,
                action="document_version_create",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={
                    "document_id": document_id,
                    "external_id": external_id,
                    "status": status,
                    "chunk_count": len(chunks),
                },
            )

    return {
        "document_id": document_id,
        "version_id": version_id,
        "external_id": external_id,
        "title": title,
        "version_number": int(next_version),
        "status": status,
        "chunk_count": len(chunks),
        "checksum": checksum,
        "metadata": metadata.model_dump(),
    }


def insert_chunks(conn: Connection[Any], document_id: str, version_id: str, chunks: list[dict[str, Any]]) -> None:
    rows = [
        (
            str(uuid.uuid4()),
            document_id,
            version_id,
            chunk["chunk_index"],
            chunk["section"],
            chunk["heading"],
            chunk["content"],
            chunk["token_count"],
            vector_literal(chunk["embedding"]),
            json.dumps(chunk.get("metadata", {})),
        )
        for chunk in chunks
    ]
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ai_chunks (
              id, document_id, version_id, chunk_index, section, heading, content,
              token_count, embedding, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
            """,
            rows,
        )


def publish_version(version_id: str, actor: str) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            row = publish_version_tx(conn, version_id, actor)
            audit_tx(
                conn,
                actor=actor,
                action="document_version_publish",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={"document_id": str(row["document_id"]), "version_number": row["version_number"]},
            )
            return dict(row)


def publish_version_tx(conn: Connection[Any], version_id: str, actor: str) -> dict[str, Any]:
    conn.row_factory = dict_row
    row = conn.execute(
        """
        SELECT id, document_id, version_number
        FROM ai_document_versions
        WHERE id = %s
        FOR UPDATE
        """,
        (version_id,),
    ).fetchone()
    if not row:
        raise LookupError("version_not_found")

    conn.execute(
        """
        UPDATE ai_document_versions
        SET status = 'archived', archived_at = now()
        WHERE document_id = %s AND status = 'published' AND id <> %s
        """,
        (row["document_id"], version_id),
    )
    conn.execute(
        """
        UPDATE ai_document_versions
        SET status = 'published', approved_by = %s, published_at = COALESCE(published_at, now()), archived_at = NULL
        WHERE id = %s
        """,
        (actor, version_id),
    )
    conn.execute(
        "UPDATE ai_documents SET current_version_id = %s, status = 'active', updated_at = now() WHERE id = %s",
        (version_id, row["document_id"]),
    )
    return row


def archive_document(document_id: str, actor: str) -> None:
    with connection() as conn:
        with conn.transaction():
            updated = conn.execute(
                """
                UPDATE ai_documents
                SET status = 'archived', current_version_id = NULL, updated_at = now()
                WHERE id = %s
                """,
                (document_id,),
            ).rowcount
            if not updated:
                raise LookupError("document_not_found")
            conn.execute(
                "UPDATE ai_document_versions SET status = 'archived', archived_at = now() WHERE document_id = %s",
                (document_id,),
            )
            audit_tx(
                conn,
                actor=actor,
                action="document_archive",
                entity_type="ai_document",
                entity_id=document_id,
                metadata={},
            )


def list_documents() -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT d.id::text AS document_id,
                   d.external_id,
                   d.title,
                   COALESCE(c.metadata->>'source_filename', d.source_filename) AS source_filename,
                   d.status,
                   d.current_version_id::text AS latest_version_id,
                   v.version_number AS latest_version_number,
                   v.status AS latest_version_status,
                   d.updated_at,
                   d.metadata
            FROM ai_documents d
            LEFT JOIN ai_document_versions v ON v.id = d.current_version_id
            ORDER BY d.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def list_versions(document_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS version_id,
                   document_id::text AS document_id,
                   version_number,
                   status,
                   checksum,
                   chunk_count,
                   change_summary,
                   published_at,
                   archived_at,
                   created_at
            FROM ai_document_versions
            WHERE document_id = %s
            ORDER BY version_number DESC
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_taxonomy_intents(status: str = "active") -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   intent_key,
                   domain,
                   audience,
                   related_tags,
                   risk_level,
                   status,
                   created_at,
                   updated_at
            FROM taxonomy_intents
            WHERE (%s = '' OR status = %s)
            ORDER BY domain, intent_key
            """,
            (status, status),
        ).fetchall()
        return [dict(row) for row in rows]


def list_synonym_groups(status: str = "", include_terms: bool = True) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   canonical_key,
                   synonym_type,
                   domain,
                   audience,
                   status,
                   created_by,
                   approved_by,
                   created_at,
                   updated_at
            FROM search_synonym_groups
            WHERE (%s = '' OR status = %s)
            ORDER BY updated_at DESC, canonical_key
            """,
            (status, status),
        ).fetchall()
        groups = [dict(row) for row in rows]

        if not include_terms or not groups:
            for group in groups:
                group["terms"] = []
            return groups

        group_ids = [group["id"] for group in groups]
        term_rows = conn.execute(
            """
            SELECT id::text AS id,
                   group_id::text AS group_id,
                   term,
                   normalized_term,
                   language
            FROM search_synonym_terms
            WHERE group_id = ANY(%s)
            ORDER BY term
            """,
            (group_ids,),
        ).fetchall()
        by_group: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
        for row in term_rows:
            term = dict(row)
            by_group.setdefault(term.pop("group_id"), []).append(term)
        for group in groups:
            group["terms"] = by_group.get(group["id"], [])
        return groups


def active_synonym_groups() -> list[dict[str, Any]]:
    global _synonym_cache
    now = time.monotonic()
    expires_at, groups = _synonym_cache
    if expires_at > now:
        return groups
    groups = list_synonym_groups("active")
    _synonym_cache = (now + SYNONYM_CACHE_SECONDS, groups)
    return groups


def invalidate_synonym_cache() -> None:
    global _synonym_cache
    _synonym_cache = (0, [])


def create_synonym_group(request: SynonymGroupCreateRequest) -> dict[str, Any]:
    group_id = str(uuid.uuid4())
    terms = [term.term if hasattr(term, "term") else str(term) for term in request.terms]
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO search_synonym_groups (
                  id, canonical_key, synonym_type, domain, audience, status, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    group_id,
                    normalize_canonical_key(request.canonical_key),
                    request.synonym_type,
                    request.domain,
                    request.audience,
                    request.status,
                    request.created_by,
                ),
            )
            upsert_synonym_terms_tx(conn, group_id, terms)
            audit_tx(
                conn,
                actor=request.created_by,
                action="synonym_group_create",
                entity_type="search_synonym_group",
                entity_id=group_id,
                metadata={
                    "canonical_key": request.canonical_key,
                    "synonym_type": request.synonym_type,
                    "status": request.status,
                    "term_count": len(terms),
                },
            )
    invalidate_synonym_cache()
    return get_synonym_group(group_id)


def get_synonym_group(group_id: str) -> dict[str, Any]:
    groups = [group for group in list_synonym_groups("", True) if group["id"] == group_id]
    if not groups:
        raise LookupError("synonym_group_not_found")
    return groups[0]


def update_synonym_status(group_id: str, status: str, actor: str) -> dict[str, Any]:
    approved_by = actor if status == "active" else None
    with connection() as conn:
        with conn.transaction():
            rowcount = conn.execute(
                """
                UPDATE search_synonym_groups
                SET status = %s,
                    approved_by = COALESCE(%s, approved_by),
                    updated_at = now()
                WHERE id = %s
                """,
                (status, approved_by, group_id),
            ).rowcount
            if not rowcount:
                raise LookupError("synonym_group_not_found")
            audit_tx(
                conn,
                actor=actor,
                action=f"synonym_group_{status}",
                entity_type="search_synonym_group",
                entity_id=group_id,
                metadata={"status": status},
            )
    invalidate_synonym_cache()
    return get_synonym_group(group_id)


def upsert_synonym_terms_tx(conn: Connection[Any], group_id: str, terms: list[str]) -> None:
    for term in terms:
        normalized = normalize_phrase(term)
        if not normalized:
            continue
        conn.execute(
            """
            INSERT INTO search_synonym_terms (group_id, term, normalized_term, language)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (group_id, normalized_term) DO UPDATE
            SET term = EXCLUDED.term,
                language = EXCLUDED.language
            """,
            (group_id, term.strip(), normalized, detect_language(normalized)),
        )


def detect_language(normalized_term: str) -> str:
    english_markers = {"missing", "item", "wrong", "refund", "cashback", "cancel", "ride"}
    if any(marker in normalized_term.split() for marker in english_markers):
        return "en"
    return "vi"


def normalize_canonical_key(value: str) -> str:
    return normalize_phrase(value).replace(" ", "_")


def meilisearch_synonyms_payload() -> dict[str, list[str]]:
    payload: dict[str, list[str]] = {}
    for group in active_synonym_groups():
        canonical = normalize_phrase(group["canonical_key"])
        terms = [normalize_phrase(term["term"]) for term in group.get("terms", [])]
        terms = [term for term in terms if term]
        if group["synonym_type"] == "regular":
            payload[canonical] = sorted(set([*payload.get(canonical, []), *terms]))
            for term in terms:
                payload[term] = sorted(set([*payload.get(term, []), canonical, *[item for item in terms if item != term]]))
        elif group["synonym_type"] in {"one_way", "typo_correction"}:
            for term in terms:
                payload[term] = sorted(set([*payload.get(term, []), canonical]))
    return payload


def generate_synonym_suggestions(days: int, min_count: int, limit: int) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT query,
                   COUNT(*) AS search_count,
                   MAX(created_at) AS last_seen_at
            FROM ai_retrieval_events
            WHERE created_at >= now() - (%s::text || ' days')::interval
              AND result_count = 0
            GROUP BY query
            HAVING COUNT(*) >= %s
            ORDER BY search_count DESC, last_seen_at DESC
            LIMIT %s
            """,
            (days, min_count, limit),
        ).fetchall()

        suggestions: list[dict[str, Any]] = []
        for row in rows:
            query = str(row["query"])
            normalized_query = normalize_phrase(query)
            if not normalized_query:
                continue
            canonical = infer_canonical_key(normalized_query)
            confidence = infer_suggestion_confidence(normalized_query, int(row["search_count"]), bool(canonical))
            evidence = {
                "query": query,
                "normalized_query": normalized_query,
                "search_count": int(row["search_count"]),
                "last_seen_at": row["last_seen_at"].isoformat() if row["last_seen_at"] else "",
                "reason": "zero-result retrieval query with repeated demand",
            }
            duplicate = conn.execute(
                """
                SELECT id
                FROM search_synonym_suggestions
                WHERE evidence->>'normalized_query' = %s
                  AND status = 'pending'
                LIMIT 1
                """,
                (normalized_query,),
            ).fetchone()
            if duplicate:
                continue
            suggestion_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO search_synonym_suggestions (
                  id, canonical_key, suggested_terms, source, confidence, status, evidence
                )
                VALUES (%s, %s, %s::jsonb, 'ai_zero_result_cluster', %s, 'pending', %s::jsonb)
                """,
                (suggestion_id, canonical, json.dumps([query]), confidence, json.dumps(evidence)),
            )
            suggestions.append(
                {
                    "id": suggestion_id,
                    "canonical_key": canonical,
                    "suggested_terms": [query],
                    "source": "ai_zero_result_cluster",
                    "confidence": float(confidence),
                    "status": "pending",
                    "evidence": evidence,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return suggestions


def accept_synonym_suggestion(suggestion_id: str, request: SynonymSuggestionAcceptRequest) -> dict[str, Any]:
    with connection() as conn:
        conn.row_factory = dict_row
        suggestion = conn.execute(
            """
            SELECT id::text AS id,
                   canonical_key,
                   suggested_terms,
                   status
            FROM search_synonym_suggestions
            WHERE id = %s
            """,
            (suggestion_id,),
        ).fetchone()
    if not suggestion:
        raise LookupError("synonym_suggestion_not_found")
    if suggestion["status"] != "pending":
        raise ValueError("synonym_suggestion_not_pending")

    canonical_key = normalize_canonical_key(request.canonical_key or suggestion["canonical_key"])
    if not canonical_key:
        raise ValueError("canonical_key_required")

    group = create_synonym_group(
        SynonymGroupCreateRequest(
            canonical_key=canonical_key,
            synonym_type=request.synonym_type,
            status="in_review" if request.submit_review else "draft",
            terms=list(suggestion["suggested_terms"] or []),
            created_by=request.actor,
        )
    )

    with connection() as conn:
        conn.execute(
            """
            UPDATE search_synonym_suggestions
            SET status = 'accepted',
                canonical_key = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (canonical_key, suggestion_id),
        )
    return group


def list_synonym_suggestions(status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   canonical_key,
                   suggested_terms,
                   source,
                   confidence,
                   status,
                   evidence,
                   created_at,
                   updated_at
            FROM search_synonym_suggestions
            WHERE (%s = '' OR status = %s)
            ORDER BY confidence DESC, created_at DESC
            LIMIT %s
            """,
            (status, status, limit),
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["confidence"] = float(item["confidence"])
            output.append(item)
        return output


def infer_canonical_key(normalized_query: str) -> str:
    groups = active_synonym_groups()
    for group in groups:
        terms = [normalize_phrase(term["term"]) for term in group.get("terms", [])]
        if any(term and term in normalized_query for term in terms):
            return str(group["canonical_key"])

    token_set = set(tokenize(normalized_query))
    rules = [
        ("missing_item", {"thieu", "mon"}),
        ("missing_item", {"nhan", "du", "mon"}),
        ("wrong_item", {"sai", "mon"}),
        ("refund", {"hoan", "tien"}),
        ("cancel_trip", {"huy", "cuoc"}),
    ]
    for canonical, required_tokens in rules:
        if required_tokens.issubset(token_set):
            return canonical
    return ""


def infer_suggestion_confidence(normalized_query: str, search_count: int, has_canonical: bool) -> float:
    base = 0.48 + min(search_count, 10) * 0.035
    if has_canonical:
        base += 0.2
    if len(tokenize(normalized_query)) >= 3:
        base += 0.05
    return round(min(base, 0.94), 4)




def lexical_search(query: str, filters: RetrievalFilters, limit: int) -> list[dict[str, Any]]:
    tsquery = lexical_tsquery(query)
    if not tsquery:
        return []
    where_sql, params = filter_sql(filters)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id,
                   c.document_id,
                   c.version_id,
                   d.title,
                   COALESCE(c.metadata->>'source_filename', d.source_filename) AS source_filename,
                   v.version_number,
                   c.chunk_index,
                   c.section,
                   c.heading,
                   c.content,
                   c.metadata,
                   ts_rank_cd(to_tsvector('simple', immutable_unaccent(c.content)), to_tsquery('simple', %s)) AS score
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE {where_sql}
              AND to_tsvector('simple', immutable_unaccent(c.content)) @@ to_tsquery('simple', %s)
            ORDER BY score DESC, v.published_at DESC NULLS LAST
            LIMIT %s
            """,
            [tsquery, *params, tsquery, limit],
        ).fetchall()
        return [dict(row) for row in rows]


def vector_search(vector: list[float], filters: RetrievalFilters, limit: int) -> list[dict[str, Any]]:
    where_sql, params = filter_sql(filters)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id,
                   c.document_id,
                   c.version_id,
                   d.title,
                   d.source_filename,
                   v.version_number,
                   c.chunk_index,
                   c.section,
                   c.heading,
                   c.content,
                   c.metadata,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            [vector_literal(vector), *params, vector_literal(vector), limit],
        ).fetchall()
        return [dict(row) for row in rows]


def filter_sql(filters: RetrievalFilters) -> tuple[str, list[Any]]:
    clauses = ["d.status = 'active'"]
    params: list[Any] = []

    statuses = filters.status or ["published"]
    clauses.append("v.status = ANY(%s)")
    params.append(statuses)

    # Default retrieval is strict latest-published only.
    if statuses == ["published"]:
        clauses.append("d.current_version_id = v.id")

    if filters.document_ids:
        clauses.append("c.document_id = ANY(%s)")
        params.append(filters.document_ids)
    if filters.audience:
        clauses.append("(d.metadata->'audience') ?| %s")
        params.append(filters.audience)
    if filters.tags:
        clauses.append("(d.metadata->'tags') ?| %s")
        params.append(filters.tags)
    if filters.case_reasons:
        clauses.append("(d.metadata->'case_reasons') ?| %s")
        params.append(filters.case_reasons)
    if filters.vertical:
        clauses.append("d.metadata->>'vertical' = ANY(%s)")
        params.append(filters.vertical)
    if filters.category:
        clauses.append("d.metadata->>'category' = ANY(%s)")
        params.append(filters.category)

    return " AND ".join(clauses), params


def lexical_tsquery(query: str) -> str:
    terms = []
    seen = set()
    for token in tokenize(query):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return " | ".join(terms)


def log_retrieval(query: str, filters: dict[str, Any], mode: str, result_count: int, started_at: float) -> int:
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_retrieval_events (id, query, filters, mode, result_count, latency_ms)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            """,
            (str(uuid.uuid4()), query, json.dumps(filters), mode, result_count, latency_ms),
        )
    return latency_ms


def audit_tx(
    conn: Connection[Any],
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO ai_audit_events (id, actor, action, entity_type, entity_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (str(uuid.uuid4()), actor, action, entity_type, entity_id, json.dumps(metadata)),
    )
