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
from app.text_processing import normalize_phrase, render_pdf_page_jpeg, tokenize


pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
_synonym_cache: tuple[float, list[dict[str, Any]]] = (0, [])
SYNONYM_CACHE_SECONDS = 30


def pg_text(value: Any) -> str:
    return str(value or "").replace("\x00", "")


def metadata_storage_json(metadata: DocumentMetadata) -> str:
    payload = metadata.model_dump()
    payload.pop("pipeline_artifacts", None)
    return pg_text(json.dumps(payload))


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
              document_type text NOT NULL DEFAULT 'unknown',
              review_status text NOT NULL DEFAULT 'needs_review',
              extraction_confidence numeric NOT NULL DEFAULT 0,
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
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS document_type text NOT NULL DEFAULT 'unknown'")
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'needs_review'")
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS extraction_confidence numeric NOT NULL DEFAULT 0")
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
            CREATE TABLE IF NOT EXISTS ai_document_sources (
              version_id uuid PRIMARY KEY REFERENCES ai_document_versions(id) ON DELETE CASCADE,
              document_id uuid NOT NULL REFERENCES ai_documents(id) ON DELETE CASCADE,
              source_filename text NOT NULL,
              content_type text NOT NULL,
              raw_data bytea NOT NULL,
              byte_size integer NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extraction_jobs (
              id uuid PRIMARY KEY,
              document_id uuid NOT NULL REFERENCES ai_documents(id) ON DELETE CASCADE,
              version_id uuid NOT NULL REFERENCES ai_document_versions(id) ON DELETE CASCADE,
              status text NOT NULL DEFAULT 'pending',
              current_stage text NOT NULL DEFAULT 'map',
              source_type text NOT NULL DEFAULT '',
              document_type text NOT NULL DEFAULT 'unknown',
              risk_level text NOT NULL DEFAULT '',
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extraction_stage_outputs (
              id uuid PRIMARY KEY,
              job_id uuid NOT NULL REFERENCES extraction_jobs(id) ON DELETE CASCADE,
              stage text NOT NULL,
              artifact_type text NOT NULL,
              payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              status text NOT NULL DEFAULT 'completed',
              error text NOT NULL DEFAULT '',
              created_at timestamptz NOT NULL DEFAULT now()
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
            CREATE TABLE IF NOT EXISTS ai_chat_events (
              id uuid PRIMARY KEY,
              question text NOT NULL,
              answer text NOT NULL,
              citation_count integer NOT NULL DEFAULT 0,
              confidence numeric NOT NULL DEFAULT 0,
              warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
              source_chunk_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
              latency_ms integer NOT NULL DEFAULT 0,
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_sources_document ON ai_document_sources(document_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_jobs_version ON extraction_jobs(version_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_stage_outputs_job ON extraction_stage_outputs(job_id, stage)")
        conn.execute("DROP INDEX IF EXISTS idx_ai_chunks_content_fts")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_content_unaccent_fts ON ai_chunks USING gin (to_tsvector('simple', immutable_unaccent(content)))")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_metadata ON ai_chunks USING gin (metadata)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops)"
        )
        ensure_search_taxonomy_schema(conn)
        seed_search_taxonomy(conn)


def health_check() -> dict[str, Any]:
    start = time.perf_counter()
    with connection() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "healthy",
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "detail": "Postgres and pgvector schema are reachable",
    }


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
    # Business taxonomy and synonyms are curated data, not application defaults.
    # New environments start empty; CS Ops/Lead seeds and approves terms through
    # the taxonomy/synonym workflow or AI-generated suggestions.
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
    document_type: str = "unknown",
    review_status: str = "needs_review",
    extraction_confidence: float = 0.0,
    raw_data: bytes = b"",
) -> dict[str, Any]:
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    metadata_json = metadata_storage_json(metadata)
    clean_external_id = pg_text(external_id)
    clean_raw_text = pg_text(raw_text)
    clean_title = pg_text(title)
    clean_source_filename = pg_text(source_filename)
    clean_content_type = pg_text(content_type)
    clean_change_summary = pg_text(change_summary)
    clean_document_type = pg_text(document_type)
    clean_review_status = pg_text(review_status)
    clean_created_by = pg_text(created_by)

    with connection() as conn:
        with conn.transaction():
            existing = conn.execute(
                "SELECT id FROM ai_documents WHERE external_id = %s",
                (clean_external_id,),
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
                    (clean_title, clean_source_filename, clean_content_type, metadata_json, document_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ai_documents (
                      id, external_id, title, source_filename, content_type, status, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active', %s::jsonb)
                    """,
                    (document_id, clean_external_id, clean_title, clean_source_filename, clean_content_type, metadata_json),
                )

            next_version = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM ai_document_versions WHERE document_id = %s",
                (document_id,),
            ).fetchone()[0]

            conn.execute(
                """
                INSERT INTO ai_document_versions (
                  id, document_id, version_number, status, checksum, change_summary, raw_text,
                  chunk_count, document_type, review_status, extraction_confidence,
                  created_by, approved_by, effective_from, published_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), CASE WHEN %s = 'published' THEN now() ELSE NULL END)
                """,
                (
                    version_id,
                    document_id,
                    next_version,
                    status,
                    checksum,
                    clean_change_summary,
                    clean_raw_text,
                    len(chunks),
                    clean_document_type,
                    "approved" if status == "published" else clean_review_status,
                    extraction_confidence,
                    clean_created_by,
                    clean_created_by if status == "published" else None,
                    status,
                ),
            )

            if raw_data:
                conn.execute(
                    """
                    INSERT INTO ai_document_sources (
                      version_id, document_id, source_filename, content_type, raw_data, byte_size
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (version_id) DO UPDATE
                    SET source_filename = EXCLUDED.source_filename,
                        content_type = EXCLUDED.content_type,
                        raw_data = EXCLUDED.raw_data,
                        byte_size = EXCLUDED.byte_size
                    """,
                    (version_id, document_id, clean_source_filename, clean_content_type, raw_data, len(raw_data)),
                )

            insert_chunks(conn, document_id, version_id, chunks)
            job_id = persist_extraction_pipeline_artifacts(
                conn,
                document_id=document_id,
                version_id=version_id,
                metadata=metadata,
            )

            if status == "published":
                publish_version_tx(conn, version_id, created_by)

            audit_tx(
                conn,
                actor=clean_created_by,
                action="document_version_create",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={
                    "document_id": document_id,
                    "external_id": clean_external_id,
                    "status": status,
                    "chunk_count": len(chunks),
                    "document_type": document_type,
                    "review_status": review_status,
                    "extraction_confidence": extraction_confidence,
                    "extraction_job_id": job_id,
                },
            )

    return {
        "document_id": document_id,
        "version_id": version_id,
        "external_id": clean_external_id,
        "title": clean_title,
        "version_number": int(next_version),
        "status": status,
        "chunk_count": len(chunks),
        "checksum": checksum,
        "document_type": clean_document_type,
        "review_status": "approved" if status == "published" else clean_review_status,
        "extraction_confidence": extraction_confidence,
        "metadata": metadata.model_dump(),
    }


def replace_document_version_extraction(
    *,
    document_id: str,
    version_id: str,
    raw_text: str,
    chunks: list[dict[str, Any]],
    metadata: DocumentMetadata,
    document_type: str,
    review_status: str,
    extraction_confidence: float,
    actor: str,
    change_summary: str = "",
) -> None:
    metadata_json = metadata_storage_json(metadata)
    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM ai_chunks WHERE version_id = %s", (version_id,))
            insert_chunks(conn, document_id, version_id, chunks)
            conn.execute("DELETE FROM extraction_jobs WHERE version_id = %s", (version_id,))
            job_id = persist_extraction_pipeline_artifacts(
                conn,
                document_id=document_id,
                version_id=version_id,
                metadata=metadata,
            )
            conn.execute(
                """
                UPDATE ai_document_versions
                SET raw_text = %s,
                    chunk_count = %s,
                    document_type = %s,
                    review_status = %s,
                    extraction_confidence = %s,
                    change_summary = COALESCE(NULLIF(%s, ''), change_summary)
                WHERE id = %s
                """,
                (
                    pg_text(raw_text),
                    len(chunks),
                    pg_text(document_type),
                    pg_text(review_status),
                    extraction_confidence,
                    pg_text(change_summary),
                    version_id,
                ),
            )
            conn.execute(
                """
                UPDATE ai_documents
                SET metadata = %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (metadata_json, document_id),
            )
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="document_version_extraction_replace",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={
                    "document_id": document_id,
                    "chunk_count": len(chunks),
                    "document_type": document_type,
                    "review_status": review_status,
                    "extraction_confidence": extraction_confidence,
                    "extraction_job_id": job_id,
                },
            )


def insert_chunks(conn: Connection[Any], document_id: str, version_id: str, chunks: list[dict[str, Any]]) -> None:
    rows = [
        (
            str(uuid.uuid4()),
            document_id,
            version_id,
            chunk["chunk_index"],
            pg_text(chunk["section"]),
            pg_text(chunk["heading"]),
            pg_text(chunk["content"]),
            chunk["token_count"],
            vector_literal(chunk["embedding"]),
            pg_text(json.dumps(chunk.get("metadata", {}))),
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


def persist_extraction_pipeline_artifacts(
    conn: Connection[Any],
    *,
    document_id: str,
    version_id: str,
    metadata: DocumentMetadata,
) -> str:
    metadata_payload = metadata.model_dump()
    artifacts = metadata_payload.get("pipeline_artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    artifacts = [
        *artifacts,
        build_reduce_reconcile_artifact(conn, document_id=document_id, version_id=version_id, metadata_payload=metadata_payload),
    ]
    status = str(metadata_payload.get("pipeline_job_status") or ("degraded" if metadata_payload.get("extraction_status") == "degraded" else "completed"))
    current_stage = str(metadata_payload.get("pipeline_current_stage") or "verify")
    source_type = str(metadata_payload.get("source_type") or artifact_payload_value(artifacts, "classification_result", "source_type") or "")
    document_type = str(metadata_payload.get("document_type") or artifact_payload_value(artifacts, "classification_result", "document_type") or "unknown")
    risk_level = str(metadata_payload.get("risk_level") or artifact_payload_value(artifacts, "classification_result", "risk_level") or "")
    job_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO extraction_jobs (
          id, document_id, version_id, status, current_stage, source_type, document_type, risk_level
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            job_id,
            document_id,
            version_id,
            status,
            current_stage,
            source_type,
            document_type,
            risk_level,
        ),
    )
    rows = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        rows.append(
            (
                str(uuid.uuid4()),
                job_id,
                pg_text(artifact.get("stage")),
                pg_text(artifact.get("artifact_type")),
                pg_text(json.dumps(artifact.get("payload") or {})),
                pg_text(artifact.get("status") or "completed"),
                pg_text(artifact.get("error") or ""),
            )
        )
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO extraction_stage_outputs (
                  id, job_id, stage, artifact_type, payload, status, error
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                rows,
            )
    return job_id


def artifact_payload_value(artifacts: list[Any], artifact_type: str, key: str) -> Any:
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("artifact_type") != artifact_type:
            continue
        payload = artifact.get("payload")
        if isinstance(payload, dict) and payload.get(key):
            return payload.get(key)
    return ""


def build_reduce_reconcile_artifact(
    conn: Connection[Any],
    *,
    document_id: str,
    version_id: str,
    metadata_payload: dict[str, Any],
) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        current = cur.execute(
            """
            SELECT id::text AS document_id, external_id, title, metadata
            FROM ai_documents
            WHERE id = %s
            """,
            (document_id,),
        ).fetchone()
        other_docs = cur.execute(
            """
            SELECT id::text AS document_id, external_id, title, status, metadata
            FROM ai_documents
            WHERE id <> %s
            ORDER BY updated_at DESC
            LIMIT 200
            """,
            (document_id,),
        ).fetchall()
        version_rows = cur.execute(
            """
            SELECT id::text AS version_id, version_number, status, review_status, created_at
            FROM ai_document_versions
            WHERE document_id = %s AND id <> %s
            ORDER BY version_number DESC
            LIMIT 10
            """,
            (document_id, version_id),
        ).fetchall()

    current_title = str((current or {}).get("title") or metadata_payload.get("title") or "")
    current_title_norm = normalize_phrase(current_title)
    current_tokens = significant_tokens(current_title_norm)
    current_tags = normalized_set(metadata_payload.get("tags"))
    current_case_reasons = normalized_set(metadata_payload.get("case_reasons"))
    current_category = normalize_phrase(str(metadata_payload.get("category") or ""))
    current_vertical = normalize_phrase(str(metadata_payload.get("vertical") or ""))

    duplicate_title: list[dict[str, Any]] = []
    related_sop: list[dict[str, Any]] = []
    possible_conflict: list[dict[str, Any]] = []
    for row in other_docs:
        doc_metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        title = str(row.get("title") or "")
        title_norm = normalize_phrase(title)
        title_tokens = significant_tokens(title_norm)
        title_overlap = overlap_score(current_tokens, title_tokens)
        tags = normalized_set(doc_metadata.get("tags"))
        case_reasons = normalized_set(doc_metadata.get("case_reasons"))
        category = normalize_phrase(str(doc_metadata.get("category") or ""))
        vertical = normalize_phrase(str(doc_metadata.get("vertical") or ""))
        tag_overlap = len(current_tags & tags)
        case_reason_overlap = len(current_case_reasons & case_reasons)
        metadata_overlap = tag_overlap + case_reason_overlap + int(bool(current_category and current_category == category)) + int(bool(current_vertical and current_vertical == vertical))

        if current_title_norm and (current_title_norm == title_norm or title_overlap >= 0.82):
            duplicate_title.append(
                {
                    "document_id": row["document_id"],
                    "title": title,
                    "status": row.get("status"),
                    "reason": "same_or_highly_similar_title",
                    "score": round(title_overlap, 2),
                }
            )
        if metadata_overlap >= 2:
            related_sop.append(
                {
                    "document_id": row["document_id"],
                    "title": title,
                    "status": row.get("status"),
                    "reason": "metadata_overlap",
                    "matched_tags": sorted(current_tags & tags)[:8],
                    "matched_case_reasons": sorted(current_case_reasons & case_reasons)[:8],
                    "score": metadata_overlap,
                }
            )
        if metadata_overlap >= 2 and title_overlap < 0.35:
            possible_conflict.append(
                {
                    "document_id": row["document_id"],
                    "title": title,
                    "status": row.get("status"),
                    "reason": "same_operational_area_different_title_review_for_conflict",
                    "score": round(metadata_overlap + title_overlap, 2),
                }
            )

    duplicate_title = sorted(duplicate_title, key=lambda item: item["score"], reverse=True)[:5]
    related_sop = sorted(related_sop, key=lambda item: item["score"], reverse=True)[:8]
    possible_conflict = sorted(possible_conflict, key=lambda item: item["score"], reverse=True)[:5]
    possible_newer_version = [
        {
            "version_id": row["version_id"],
            "version_number": row["version_number"],
            "status": row["status"],
            "review_status": row["review_status"],
            "reason": "same_document_existing_version",
        }
        for row in version_rows
    ]

    return {
        "artifact_type": "reconcile_suggestions",
        "error": "",
        "payload": {
            "auto_apply": False,
            "duplicate_title": duplicate_title,
            "possible_newer_version": possible_newer_version,
            "related_sop": related_sop,
            "possible_conflict": possible_conflict,
            "summary": {
                "duplicate_title_count": len(duplicate_title),
                "related_sop_count": len(related_sop),
                "possible_conflict_count": len(possible_conflict),
                "same_document_version_count": len(possible_newer_version),
            },
        },
        "stage": "reduce",
        "status": "completed",
    }


def normalized_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {normalize_phrase(str(item)) for item in value if normalize_phrase(str(item))}


def significant_tokens(value: str) -> set[str]:
    return {token for token in value.split() if len(token) > 2}


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def list_extraction_pipeline(version_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        jobs = conn.execute(
            """
            SELECT id::text AS id,
                   document_id::text AS document_id,
                   version_id::text AS version_id,
                   status,
                   current_stage,
                   source_type,
                   document_type,
                   risk_level,
                   created_at,
                   updated_at
            FROM extraction_jobs
            WHERE version_id = %s
            ORDER BY created_at DESC
            """,
            (version_id,),
        ).fetchall()
        if not jobs:
            return []
        job_ids = [row["id"] for row in jobs]
        outputs = conn.execute(
            """
            SELECT id::text AS id,
                   job_id::text AS job_id,
                   stage,
                   artifact_type,
                   payload,
                   status,
                   error,
                   created_at
            FROM extraction_stage_outputs
            WHERE job_id::text = ANY(%s)
            ORDER BY created_at, stage, artifact_type
            """,
            (job_ids,),
        ).fetchall()
    outputs_by_job: dict[str, list[dict[str, Any]]] = {}
    for output in outputs:
        item = dict(output)
        outputs_by_job.setdefault(item["job_id"], []).append(item)
    return [
        {
            **dict(job),
            "outputs": outputs_by_job.get(job["id"], []),
        }
        for job in jobs
    ]


def publish_version(version_id: str, actor: str, force: bool = False) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            if not force:
                validate_publish_readiness_tx(conn, version_id)
            row = publish_version_tx(conn, version_id, actor, force=force)
            audit_tx(
                conn,
                actor=actor,
                action="document_version_force_publish" if force else "document_version_publish",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={"document_id": str(row["document_id"]), "force": force, "version_number": row["version_number"]},
            )
            return dict(row)


def publish_readiness(version_id: str) -> dict[str, Any]:
    with connection() as conn:
        try:
            validate_publish_readiness_tx(conn, version_id)
        except ValueError as exc:
            detail = str(exc)
            if not detail.startswith("publish_readiness_failed:"):
                raise
            failures = [
                failure
                for failure in detail.removeprefix("publish_readiness_failed:").split(",")
                if failure
            ]
            return {
                "ready": False,
                "failure_count": len(failures),
                "failures": failures,
            }
        return {
            "ready": True,
            "failure_count": 0,
            "failures": [],
        }


def has_required_source_ref(document_type: str, metadata: dict[str, Any]) -> bool:
    refs = metadata.get("source_refs")
    if not isinstance(refs, list):
        refs = []
    if document_type == "policy_table":
        return bool(metadata.get("source_sheet")) or any(isinstance(ref, dict) and ref.get("sheet") for ref in refs)
    if document_type == "workflow_diagram":
        return bool(metadata.get("source_page") or metadata.get("page_number")) or any(
            isinstance(ref, dict) and ref.get("page") for ref in refs
        )
    if document_type == "policy_rule":
        return any(
            isinstance(ref, dict)
            and (
                ref.get("paragraph_index") is not None
                or ref.get("heading_path")
                or ref.get("line_start")
                or ref.get("page")
                or (ref.get("table_index") is not None and ref.get("row_index") is not None)
            )
            for ref in refs
        )
    return True


def is_high_risk_metadata(metadata: dict[str, Any], normalized_text: str) -> bool:
    risk_level = normalize_phrase(str(metadata.get("risk_level") or ""))
    if risk_level in {"high", "critical"}:
        return True
    risk_terms = [
        "financial",
        "finance",
        "payment",
        "money",
        "thanh toan",
        "account",
        "tai khoan",
        "privacy",
        "bao mat",
        "security",
        "compliance",
        "tuan thu",
        "escalation",
        "rui ro",
        "vi pham",
        "canh bao",
    ]
    return any(term in normalized_text for term in risk_terms)


def has_bulk_review_blocker(document_type: str, rows: list[dict[str, Any]]) -> bool:
    if document_type == "workflow_diagram":
        return True
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        confidence = metadata.get("confidence")
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 1.0
        text = normalize_phrase(" ".join([str(row.get("heading") or ""), str(row.get("content") or ""), json.dumps(metadata, ensure_ascii=False)]))
        if confidence_value < 0.85 or is_high_risk_metadata(metadata, text):
            return True
    return False


def is_reviewed_status(value: Any) -> bool:
    return str(value or "needs_review") in {"reviewed", "approved"}


def workflow_source_ref_ack_missing(metadata: dict[str, Any]) -> bool:
    return str(metadata.get("source_ref_quality") or "") == "page_only" and metadata.get("source_ref_acknowledged") is not True


def workflow_graph_edge_count(metadata: dict[str, Any]) -> int:
    graph = metadata.get("workflow_graph")
    if not isinstance(graph, dict):
        return 0
    edges = graph.get("edges")
    return len(edges) if isinstance(edges, list) else 0


def workflow_graph_quality_failures(metadata: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    graph_errors = metadata.get("graph_validation_errors")
    uncertain_edges = metadata.get("uncertain_edges")
    uncertain_edges_count = int(metadata.get("uncertain_edges_count") or 0)
    try:
        graph_confidence = float(metadata.get("graph_confidence") or metadata.get("confidence") or 1)
    except (TypeError, ValueError):
        graph_confidence = 0
    has_quality_issue = (
        (isinstance(graph_errors, list) and bool(graph_errors))
        or (isinstance(uncertain_edges, list) and bool(uncertain_edges))
        or uncertain_edges_count > 0
        or graph_confidence < 0.7
    )
    if metadata.get("graph_validation_acknowledged") is True:
        if has_quality_issue and not str(metadata.get("graph_validation_acknowledged_reason") or "").strip():
            failures.append("workflow_graph_acknowledgement_reason_missing")
        return failures
    if isinstance(graph_errors, list) and graph_errors:
        failures.append(f"workflow_graph_has_{len(graph_errors)}_validation_errors")
    if isinstance(uncertain_edges, list) and uncertain_edges:
        failures.append(f"workflow_graph_has_{len(uncertain_edges)}_uncertain_edges")
    if uncertain_edges_count > 0:
        failures.append(f"workflow_graph_has_{uncertain_edges_count}_uncertain_edges")
    if graph_confidence < 0.7:
        failures.append("workflow_graph_low_confidence")
    return list(dict.fromkeys(failures))


def workflow_edge_key(edge: dict[str, Any]) -> str:
    from_node = str(edge.get("from_node") or edge.get("from") or edge.get("source") or "").strip()
    condition = str(edge.get("condition") or "").strip().lower()
    to_node = str(edge.get("to_node") or edge.get("to") or edge.get("target") or "").strip()
    return f"{from_node}|{condition}|{to_node}"


def workflow_graph_decision_edge_failures(metadata: dict[str, Any]) -> list[str]:
    graph = metadata.get("workflow_graph")
    if not isinstance(graph, dict):
        return []
    edges = graph.get("edges")
    nodes = graph.get("nodes")
    if not isinstance(edges, list):
        return []
    node_map: dict[str, dict[str, Any]] = {}
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                node_id = str(node.get("id") or "").strip()
                if node_id:
                    node_map[node_id] = node

    reviews = metadata.get("workflow_edge_reviews")
    if not isinstance(reviews, dict):
        reviews = {}

    decision_edges = []
    missing_review = 0
    rejected = 0
    missing_reason = 0
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if not is_workflow_decision_edge(edge, node_map):
            continue
        decision_edges.append(edge)
        edge_review = reviews.get(workflow_edge_key(edge))
        if not isinstance(edge_review, dict):
            edge_review = {}
        status = str(edge_review.get("status") or edge.get("review_status") or "").strip().lower()
        reason = str(edge_review.get("reason") or edge.get("review_reason") or "").strip()
        if status == "rejected":
            rejected += 1
            continue
        if status not in {"confirmed", "acknowledged"}:
            missing_review += 1
            continue
        if status == "acknowledged" and not reason:
            missing_reason += 1

    if not decision_edges and any(is_workflow_decision_node(node) for node in node_map.values()):
        return ["workflow_graph_decision_edges_missing"]

    failures: list[str] = []
    if missing_review:
        failures.append(f"workflow_graph_has_{missing_review}_decision_edges_need_review")
    if rejected:
        failures.append(f"workflow_graph_has_{rejected}_rejected_decision_edges")
    if missing_reason:
        failures.append(f"workflow_graph_has_{missing_reason}_edge_acknowledgements_missing_reason")
    return failures


def is_workflow_decision_edge(edge: dict[str, Any], node_map: dict[str, dict[str, Any]]) -> bool:
    condition = normalize_phrase(str(edge.get("condition") or ""))
    if condition in {"yes", "no", "co", "khong", "dung", "sai"} or "no response" in condition or "khong phan hoi" in condition:
        return True
    from_node_id = str(edge.get("from_node") or edge.get("from") or edge.get("source") or "").strip()
    node = node_map.get(from_node_id)
    if node and is_workflow_decision_node(node):
        return True
    return "decision" in normalize_phrase(from_node_id)


def is_workflow_decision_node(node: dict[str, Any]) -> bool:
    haystack = normalize_phrase(" ".join([
        str(node.get("id") or ""),
        str(node.get("type") or ""),
        str(node.get("title") or ""),
        str(node.get("question") or ""),
    ]))
    return "decision" in haystack or "quyet dinh" in haystack or bool(node.get("question")) or "?" in haystack


def required_unit_types_from_metadata(metadata: dict[str, Any]) -> set[str]:
    candidates: list[Any] = []
    for key in ("required_unit_types", "publish_required_unit_types"):
        value = metadata.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    document_metadata = metadata.get("document_metadata")
    if isinstance(document_metadata, dict):
        for key in ("required_unit_types", "publish_required_unit_types"):
            value = document_metadata.get(key)
            if isinstance(value, list):
                candidates.extend(value)
    readiness = metadata.get("publish_readiness")
    if isinstance(readiness, dict):
        value = readiness.get("required_unit_types") or readiness.get("required_units")
        if isinstance(value, list):
            candidates.extend(value)
    return {
        normalize_required_unit_type(str(item))
        for item in candidates
        if normalize_required_unit_type(str(item))
    }


def normalize_required_unit_type(value: str) -> str:
    normalized = normalize_phrase(value).replace(" ", "_").replace("-", "_")
    allowed = {
        "routing_rule",
        "operational_instruction",
        "policy_rule",
        "validation_rule",
        "handling_rule",
        "exception_rule",
        "threshold_rule",
        "workflow_step",
        "decision_point",
        "decision_rule",
        "sla_rule",
        "escalation_rule",
        "case_creation_rule",
        "handoff_rule",
        "macro_script",
        "operational_note",
        "security_note",
        "compliance_note",
        "warning",
        "related_document",
        "follow_up_rule",
        "text_section",
    }
    return normalized if normalized in allowed else ""


def missing_or_unreviewed_workflow_unit(
    unit_status_by_type: dict[str, bool],
    accepted_types: set[str],
    failure_key: str,
) -> str | None:
    present = [unit_type for unit_type in accepted_types if unit_type in unit_status_by_type]
    if not present:
        return f"missing_workflow_unit_{failure_key}"
    if not any(unit_status_by_type[unit_type] for unit_type in present):
        return f"workflow_unit_{failure_key}_needs_review"
    return None


def validate_publish_readiness_tx(conn: Connection[Any], version_id: str) -> None:
    conn.row_factory = dict_row
    version = conn.execute(
        """
        SELECT v.id::text AS version_id,
               v.document_id::text AS document_id,
               v.status,
               v.document_type,
               d.metadata
        FROM ai_document_versions v
        JOIN ai_documents d ON d.id = v.document_id
        WHERE v.id = %s
        """,
        (version_id,),
    ).fetchone()
    if not version:
        raise LookupError("version_not_found")
    if version["status"] == "archived":
        raise ValueError("publish_readiness_failed:archived_version")

    rows = conn.execute(
        """
        SELECT section, heading, content, metadata
        FROM ai_chunks
        WHERE version_id = %s
        ORDER BY chunk_index
        """,
        (version_id,),
    ).fetchall()
    failures: list[str] = []
    if not rows:
        failures.append("no_extraction_units")

    document_metadata = version.get("metadata") or {}
    if not isinstance(document_metadata, dict):
        document_metadata = {}
    document_extraction_status = str(document_metadata.get("extraction_status") or "")
    if document_extraction_status == "failed" or document_extraction_status.startswith("failed"):
        failures.append("extraction_failed_validation")

    has_full_sop = False
    pending_units = 0
    has_owner = bool(document_metadata.get("owner_team"))
    has_effective_from = False
    has_historical_sheets = False
    has_high_risk_signal = False
    has_workflow_graph = version["document_type"] != "workflow_diagram"
    workflow_graph_reviewed = version["document_type"] != "workflow_diagram"
    workflow_graph_confidence = 1.0
    workflow_graph_edges = 0
    workflow_graph_quality_errors: list[str] = []
    workflow_source_ack_missing = 0
    workflow_unit_status_by_type: dict[str, bool] = {}
    required_unit_types: set[str] = set()
    missing_source_refs = 0
    atomic_units = 0
    degraded_unconverted = 0
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        unit_extraction_status = str(metadata.get("extraction_status") or "")
        if unit_extraction_status == "failed" or unit_extraction_status.startswith("failed"):
            failures.append("extraction_failed_validation")
        unit_type = str(metadata.get("unit_type") or row.get("section") or "")
        retrieval_scope = str(metadata.get("retrieval_scope") or "")
        if retrieval_scope != "document" and unit_type != "full_sop" and not unit_type.startswith("candidate_"):
            atomic_units += 1
        if is_degraded_unconverted(metadata):
            degraded_unconverted += 1
        text = normalize_phrase(" ".join([str(row.get("heading") or ""), str(row.get("content") or ""), json.dumps(metadata, ensure_ascii=False)]))
        if unit_type:
            workflow_unit_status_by_type[unit_type] = workflow_unit_status_by_type.get(unit_type, False) or is_reviewed_status(metadata.get("review_status"))
        required_unit_types.update(required_unit_types_from_metadata(metadata))
        has_full_sop = has_full_sop or unit_type == "full_sop" or retrieval_scope == "document"
        pending_units += 1 if str(metadata.get("review_status") or "needs_review") == "needs_review" else 0
        has_owner = has_owner or bool(metadata.get("owner_team"))
        has_effective_from = has_effective_from or bool(metadata.get("effective_from"))
        has_historical_sheets = has_historical_sheets or bool(metadata.get("historical_sheets"))
        has_high_risk_signal = has_high_risk_signal or is_high_risk_metadata(metadata, text)
        if unit_type == "workflow_graph" or metadata.get("workflow_graph"):
            has_workflow_graph = True
            workflow_graph_reviewed = str(metadata.get("review_status") or "needs_review") in {"reviewed", "approved"}
            try:
                workflow_graph_confidence = float(metadata.get("graph_confidence") or metadata.get("confidence") or 0)
            except (TypeError, ValueError):
                workflow_graph_confidence = 0
            workflow_graph_edges = workflow_graph_edge_count(metadata)
            workflow_graph_quality_errors.extend(workflow_graph_quality_failures(metadata))
            workflow_graph_quality_errors.extend(workflow_graph_decision_edge_failures(metadata))
        if version["document_type"] == "workflow_diagram" and workflow_source_ref_ack_missing(metadata):
            workflow_source_ack_missing += 1
        if not has_required_source_ref(version["document_type"], metadata):
            missing_source_refs += 1

    if not has_full_sop:
        failures.append("missing_full_sop_layer")
    if version["document_type"] in {"policy_table", "policy_rule", "workflow_diagram"} and atomic_units == 0:
        failures.append("missing_production_atomic_units")
    if degraded_unconverted:
        failures.append(f"{degraded_unconverted}_degraded_units_need_manual_curation")
    if pending_units:
        failures.append(f"{pending_units}_units_need_review")
    if not has_owner:
        failures.append("missing_owner_team")
    if missing_source_refs:
        failures.append(f"{missing_source_refs}_units_missing_source_refs")
    if version["document_type"] == "workflow_diagram":
        if not has_workflow_graph:
            failures.append("missing_workflow_graph")
        if not workflow_graph_reviewed:
            failures.append("workflow_graph_needs_review")
        if has_workflow_graph and workflow_graph_edges == 0:
            failures.append("workflow_graph_missing_edges")
        failures.extend(workflow_graph_quality_errors)
        if workflow_source_ack_missing:
            failures.append(f"{workflow_source_ack_missing}_page_only_source_refs_need_ack")
        for required_unit_type in sorted(required_unit_types):
            accepted_types = {required_unit_type}
            if required_unit_type == "decision_rule":
                accepted_types.add("decision_point")
            failure = missing_or_unreviewed_workflow_unit(workflow_unit_status_by_type, accepted_types, required_unit_type)
            if failure:
                failures.append(failure)
    if version["document_type"] in {"policy_table", "policy_rule", "workflow_diagram"} and (has_high_risk_signal or has_historical_sheets) and not has_effective_from:
        failures.append("missing_effective_from")
    if has_historical_sheets and not has_effective_from:
        failures.append("historical_sheets_without_current_effective_date")

    if failures:
        raise ValueError("publish_readiness_failed:" + ",".join(failures))


def is_degraded_unconverted(metadata: dict[str, Any]) -> bool:
    extraction_status = str(metadata.get("extraction_status") or "")
    if extraction_status != "degraded":
        return False
    return not (
        metadata.get("manual_curation_status") == "converted"
        and metadata.get("extraction_status") == "manually_curated"
        and metadata.get("review_status") == "approved"
    )


def promoted_unit_type(unit_type: str, document_type: str) -> str:
    mapping = {
        "candidate_section": "text_section",
        "candidate_rule": "policy_rule",
        "candidate_warning": "warning",
        "candidate_table_row": "policy_rule",
        "candidate_workflow_text": "workflow_overview",
        "candidate_step": "workflow_step",
        "candidate_action": "workflow_step",
        "candidate_decision": "decision_point",
        "candidate_annotation": "operational_note",
        "candidate_sla": "sla_rule",
        "candidate_audit_rule": "warning",
        "candidate_queue_rule": "routing_rule",
    }
    if unit_type in mapping:
        return mapping[unit_type]
    if unit_type.startswith("candidate_"):
        return "workflow_step" if document_type == "workflow_diagram" else "text_section"
    return unit_type


def promote_degraded_candidates_tx(conn: Connection[Any], version_id: str, document_type: str, actor: str, scope: str) -> int:
    rows = conn.execute(
        """
        SELECT id::text AS id, section, metadata
        FROM ai_chunks
        WHERE version_id = %s
          AND COALESCE(metadata->>'extraction_status', '') = 'degraded'
          AND (
            %s = 'all'
            OR COALESCE(metadata->>'retrieval_scope', '') <> 'document'
            AND COALESCE(metadata->>'unit_type', '') <> 'full_sop'
          )
        FOR UPDATE
        """,
        (version_id, scope),
    ).fetchall()
    promoted_count = 0
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        existing_unit_type = str(metadata.get("unit_type") or row.get("section") or "text_section")
        next_unit_type = promoted_unit_type(existing_unit_type, document_type)
        next_metadata = {
            **metadata,
            "unit_type": next_unit_type,
            "original_unit_type": metadata.get("original_unit_type") or existing_unit_type,
            "review_status": "approved",
            "reviewed_by": actor,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "manually_curated",
            "extraction_lifecycle_status": "reviewed",
            "manual_curation_status": "converted",
            "manual_curation_method": "bulk_force_approve",
            "publish_blocked": False,
            "publish_blocked_reason": "",
            "source_evidence_only": False,
            "source_ref_acknowledged": True,
        }
        conn.execute(
            """
            UPDATE ai_chunks
            SET section = %s,
                metadata = %s::jsonb
            WHERE id = %s
            """,
            (next_unit_type, json.dumps(next_metadata), row["id"]),
        )
        promoted_count += 1
    return promoted_count


def bulk_review_version(version_id: str, actor: str, review_status: str = "reviewed", scope: str = "all", force: bool = False) -> dict[str, Any]:
    if review_status not in {"reviewed", "approved"}:
        raise ValueError("invalid_review_status")
    if scope not in {"all", "atomic"}:
        raise ValueError("invalid_review_scope")
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = conn.execute(
                """
                SELECT v.id::text AS version_id,
                       document_id::text AS document_id,
                       v.status,
                       v.document_type,
                       v.effective_from
                FROM ai_document_versions v
                WHERE v.id = %s
                FOR UPDATE
                """,
                (version_id,),
            ).fetchone()
            if not row:
                raise LookupError("version_not_found")
            if row["status"] != "draft":
                raise ValueError("published_or_archived_versions_are_immutable")
            risk_rows = conn.execute(
                """
                SELECT heading, content, metadata
                FROM ai_chunks
                WHERE version_id = %s
                """,
                (version_id,),
            ).fetchall()
            if not force and has_bulk_review_blocker(row["document_type"], risk_rows):
                raise ValueError("bulk_review_blocked_high_risk_or_low_confidence")

            effective_from = inferred_effective_from(risk_rows, row.get("effective_from"))
            updated_count = conn.execute(
                """
                UPDATE ai_chunks
                SET metadata = jsonb_set(
                  jsonb_set(
                    jsonb_set(
                      jsonb_set(
                        jsonb_set(metadata, '{review_status}', to_jsonb(%s::text), true),
                        '{reviewed_by}', to_jsonb(%s::text), true
                      ),
                      '{reviewed_at}', to_jsonb(%s::text), true
                    ),
                    '{source_ref_acknowledged}', 'true'::jsonb, true
                  ),
                  '{effective_from}', to_jsonb(COALESCE(NULLIF(metadata->>'effective_from', ''), %s)::text), true
                )
                WHERE version_id = %s
                  AND (
                    %s = 'all'
                    OR COALESCE(metadata->>'retrieval_scope', '') <> 'document'
                    AND COALESCE(metadata->>'unit_type', '') <> 'full_sop'
                  )
                """,
                (review_status, actor, datetime.now(timezone.utc).isoformat(), effective_from, version_id, scope),
            ).rowcount
            promoted_count = 0
            if force and review_status == "approved":
                promoted_count = promote_degraded_candidates_tx(conn, version_id, row["document_type"], actor, scope)
            remaining_needs_review = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM ai_chunks
                WHERE version_id = %s
                  AND COALESCE(metadata->>'review_status', 'needs_review') = 'needs_review'
                """,
                (version_id,),
            ).fetchone()["count"]
            if int(remaining_needs_review or 0) == 0:
                conn.execute(
                    """
                    UPDATE ai_document_versions
                    SET review_status = %s
                    WHERE id = %s
                    """,
                    (review_status, version_id),
                )
            conn.execute(
                "UPDATE ai_documents SET updated_at = now() WHERE id = %s",
                (row["document_id"],),
            )
            audit_tx(
                conn,
                actor=actor,
                action="document_version_bulk_review",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={"review_status": review_status, "scope": scope, "force": force, "updated_count": updated_count, "promoted_count": promoted_count},
            )
            return {
                "version_id": version_id,
                "document_id": str(row["document_id"]),
                "review_status": review_status,
                "scope": scope,
                "remaining_needs_review": int(remaining_needs_review or 0),
                "updated_count": int(updated_count or 0),
                "promoted_count": promoted_count,
            }


def inferred_effective_from(rows: list[dict[str, Any]], version_effective_from: Any) -> str:
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        value = metadata.get("effective_from") or metadata.get("effectiveFrom")
        if value:
            return str(value)
    if isinstance(version_effective_from, datetime):
        return version_effective_from.date().isoformat()
    if version_effective_from:
        return str(version_effective_from).split("T", 1)[0].split(" ", 1)[0]
    return datetime.now(timezone.utc).date().isoformat()


def publish_version_tx(conn: Connection[Any], version_id: str, actor: str, force: bool = False) -> dict[str, Any]:
    conn.row_factory = dict_row
    row = conn.execute(
        """
        SELECT id, document_id, version_number, status
        FROM ai_document_versions
        WHERE id = %s
        FOR UPDATE
        """,
        (version_id,),
    ).fetchone()
    if not row:
        raise LookupError("version_not_found")
    if row["status"] == "archived":
        raise ValueError("archived_version")

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
        SET status = 'published',
            review_status = 'approved',
            approved_by = %s,
            published_at = COALESCE(published_at, now()),
            archived_at = NULL
        WHERE id = %s
        """,
        (actor, version_id),
    )
    conn.execute(
        "UPDATE ai_documents SET current_version_id = %s, status = 'active', updated_at = now() WHERE id = %s",
        (version_id, row["document_id"]),
    )
    published = conn.execute(
        """
        SELECT v.id::text AS version_id,
               v.document_id::text AS document_id,
               d.external_id,
               d.title,
               v.version_number,
               v.status,
               v.checksum,
               v.chunk_count,
               v.document_type,
               v.review_status,
               v.extraction_confidence::float AS extraction_confidence,
               d.metadata
        FROM ai_document_versions v
        JOIN ai_documents d ON d.id = v.document_id
        WHERE v.id = %s
        """,
        (version_id,),
    ).fetchone()
    if force:
        conn.execute(
            """
            UPDATE ai_chunks
            SET metadata = jsonb_set(
              jsonb_set(
                jsonb_set(
                  jsonb_set(
                    jsonb_set(
                      jsonb_set(
                        metadata,
                        '{review_status}',
                        '"approved"'::jsonb,
                        true
                      ),
                      '{document_type}',
                      to_jsonb(%s::text),
                      true
                    ),
                    '{publish_blocked}',
                    'false'::jsonb,
                    true
                  ),
                  '{publish_blocked_reason}',
                  '""'::jsonb,
                  true
                ),
                '{publish_forced}',
                'true'::jsonb,
                true
              ),
              '{publish_forced_by}',
              to_jsonb(%s::text),
              true
            )
            WHERE version_id = %s
            """,
            (published["document_type"], actor, version_id),
        )
    else:
        conn.execute(
            """
            UPDATE ai_chunks
            SET metadata = jsonb_set(
              jsonb_set(metadata, '{review_status}', '"approved"'::jsonb, true),
              '{document_type}',
              to_jsonb(%s::text),
              true
            )
            WHERE version_id = %s
            """,
            (published["document_type"], version_id),
        )
    return dict(published)


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
                   d.source_filename,
                   d.status,
                   v.id::text AS latest_version_id,
                   v.version_number AS latest_version_number,
                   v.status AS latest_version_status,
                   v.document_type AS latest_document_type,
                   v.review_status AS latest_review_status,
                   v.extraction_confidence::float AS latest_extraction_confidence,
                   d.updated_at,
                   d.metadata
            FROM ai_documents d
            LEFT JOIN LATERAL (
              SELECT *
              FROM ai_document_versions
              WHERE document_id = d.id
              ORDER BY version_number DESC
              LIMIT 1
            ) v ON true
            ORDER BY d.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def rerank_structural_matches(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_query = normalize_phrase(query)
    query_tokens = [token for token in normalized_query.split() if len(token) >= 4]
    if not query_tokens and not normalized_query:
        return rows
    for row in rows:
        metadata = row.get("metadata") or {}
        sheet = normalize_phrase(str(metadata.get("sheet_name") or ""))
        heading = normalize_phrase(str(row.get("heading") or ""))
        section = normalize_phrase(str(row.get("section") or ""))
        structural_text = " ".join([sheet, heading, section])
        matched = sum(1 for token in query_tokens if token in structural_text)
        phrase_boost = 0.0
        if sheet and (sheet in normalized_query or normalized_query in sheet):
            phrase_boost += 3.0
        if heading and (heading in normalized_query or normalized_query in heading):
            phrase_boost += 2.0
        if matched:
            row["score"] = float(row.get("score") or 0) + matched * 0.75 + phrase_boost
        elif phrase_boost:
            row["score"] = float(row.get("score") or 0) + phrase_boost
    return sorted(rows, key=lambda row: float(row.get("score") or 0), reverse=True)


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
                   document_type,
                   review_status,
                   extraction_confidence::float AS extraction_confidence,
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


def list_chunks(document_id: str, version_id: str = "") -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        if not version_id:
            current = conn.execute(
                "SELECT current_version_id::text FROM ai_documents WHERE id = %s",
                (document_id,),
            ).fetchone()
            if not current or not current["current_version_id"]:
                return []
            version_id = str(current["current_version_id"])

        rows = conn.execute(
            """
            SELECT id::text AS chunk_id,
                   document_id::text AS document_id,
                   version_id::text AS version_id,
                   chunk_index,
                   section,
                   heading,
                   content,
                   token_count,
                   metadata,
                   created_at
            FROM ai_chunks
            WHERE document_id = %s AND version_id = %s
            ORDER BY chunk_index
            """,
            (document_id, version_id),
        ).fetchall()
        return [dict(row) for row in rows]


def list_extraction_units(document_id: str, version_id: str = "") -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        if not version_id:
            current = conn.execute(
                "SELECT current_version_id::text FROM ai_documents WHERE id = %s",
                (document_id,),
            ).fetchone()
            if not current or not current["current_version_id"]:
                return []
            version_id = str(current["current_version_id"])

        rows = conn.execute(
            """
            SELECT c.id::text AS unit_id,
                   c.document_id::text AS document_id,
                   c.version_id::text AS version_id,
                   c.chunk_index AS unit_index,
                   c.section,
                   c.heading AS title,
                   c.content,
                   c.metadata,
                   v.document_type,
                   v.review_status,
                   v.extraction_confidence::float AS extraction_confidence
            FROM ai_chunks c
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE c.document_id = %s AND c.version_id = %s
            ORDER BY c.chunk_index
            """,
            (document_id, version_id),
        ).fetchall()

    units = []
    for row in rows:
        item = dict(row)
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        source_type = str(metadata.get("source_type") or "")
        document_type = str(item.get("document_type") or "")
        units.append(
            extraction_unit_from_row(item, document_type, source_type, metadata)
        )
    return units


def extraction_unit_from_row(
    item: dict[str, Any],
    document_type: str,
    source_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    confidence = metadata.get("confidence", item.get("extraction_confidence") or 0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    return {
        "unit_id": item["unit_id"],
        "document_id": item["document_id"],
        "version_id": item["version_id"],
        "unit_index": item["unit_index"],
        "unit_type": extraction_unit_type(document_type, source_type, metadata),
        "title": item.get("title") or item.get("section") or "Đơn vị trích xuất cần review",
        "content": item["content"],
        "source_sheet": str(metadata.get("sheet_name") or ""),
        "source_row": metadata.get("row_number"),
        "source_page": metadata.get("page_number") or metadata.get("source_page"),
        "source_bbox": metadata.get("bbox") or metadata.get("source_bbox") or [],
        "confidence": confidence_value,
        "review_status": metadata.get("review_status") or item.get("review_status") or "needs_review",
        "metadata": metadata,
    }


def extraction_unit_type(document_type: str, source_type: str, metadata: dict[str, Any]) -> str:
    if metadata.get("unit_type"):
        return str(metadata["unit_type"])
    if source_type == "spreadsheet":
        return "rule_table_row"
    if source_type in {"image", "diagram_pdf"} or document_type == "workflow_diagram":
        return "workflow_or_asset_draft"
    if document_type == "macro_script":
        return "macro_or_script"
    if metadata.get("sheet_name"):
        return "table_unit"
    return "text_section"


def update_extraction_unit(
    *,
    unit_id: str,
    title: str,
    content: str,
    unit_type: str,
    confidence: float,
    review_status: str,
    metadata: dict[str, Any],
    actor: str,
    embedding: list[float],
) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = conn.execute(
                """
                SELECT c.id::text AS unit_id,
                       c.document_id::text AS document_id,
                       c.version_id::text AS version_id,
                       c.chunk_index AS unit_index,
                       c.section,
                       c.heading AS title,
                       c.content,
                       c.metadata,
                       v.status AS version_status,
                       v.document_type,
                       v.review_status,
                       v.extraction_confidence::float AS extraction_confidence
                FROM ai_chunks c
                JOIN ai_document_versions v ON v.id = c.version_id
                WHERE c.id = %s
                FOR UPDATE
                """,
                (unit_id,),
            ).fetchone()
            if not row:
                raise LookupError("extraction_unit_not_found")
            if row["version_status"] != "draft":
                raise ValueError("published_or_archived_versions_are_immutable")

            existing_metadata = row.get("metadata") or {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}
            merged_metadata = {
                **existing_metadata,
                **metadata,
                "unit_type": unit_type,
                "confidence": confidence,
                "review_status": review_status,
                "reviewed_by": actor,
            }
            if (
                existing_metadata.get("extraction_status") == "degraded"
                and review_status == "approved"
                and not unit_type.startswith("candidate_")
            ):
                merged_metadata["extraction_status"] = "manually_curated"
                merged_metadata["extraction_lifecycle_status"] = "reviewed"
                merged_metadata["manual_curation_status"] = "converted"
                merged_metadata["publish_blocked"] = False
                merged_metadata["publish_blocked_reason"] = ""
                merged_metadata["source_evidence_only"] = False
            if review_status == "reviewed":
                merged_metadata["reviewed_at"] = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """
                UPDATE ai_chunks
                SET section = %s,
                    heading = %s,
                    content = %s,
                    token_count = %s,
                    embedding = %s::vector,
                    metadata = %s::jsonb
                WHERE id = %s
                """,
                (
                    unit_type,
                    title,
                    content,
                    len(tokenize(content)),
                    vector_literal(embedding),
                    json.dumps(merged_metadata),
                    unit_id,
                ),
            )
            conn.execute(
                """
                UPDATE ai_document_versions
                SET review_status = CASE
                    WHEN review_status = 'approved' THEN review_status
                    ELSE 'reviewed'
                END
                WHERE id = %s
                """,
                (row["version_id"],),
            )
            conn.execute(
                "UPDATE ai_documents SET updated_at = now() WHERE id = %s",
                (row["document_id"],),
            )
            audit_tx(
                conn,
                actor=actor,
                action="extraction_unit_update",
                entity_type="ai_chunk",
                entity_id=unit_id,
                metadata={
                    "document_id": row["document_id"],
                    "version_id": row["version_id"],
                    "unit_type": unit_type,
                    "review_status": review_status,
                },
            )
            if metadata.get("graph_validation_acknowledged") is True and existing_metadata.get("graph_validation_acknowledged") is not True:
                audit_tx(
                    conn,
                    actor=actor,
                    action="workflow_graph_warning_acknowledge",
                    entity_type="ai_chunk",
                    entity_id=unit_id,
                    metadata={
                        "document_id": row["document_id"],
                        "version_id": row["version_id"],
                        "reason": str(metadata.get("graph_validation_acknowledged_reason") or ""),
                        "validation_errors": metadata.get("graph_validation_errors") or existing_metadata.get("graph_validation_errors") or [],
                        "uncertain_edges_count": metadata.get("uncertain_edges_count") or existing_metadata.get("uncertain_edges_count") or 0,
                    },
                )
            if "workflow_edge_reviews" in metadata:
                audit_tx(
                    conn,
                    actor=actor,
                    action="workflow_edge_review_update",
                    entity_type="ai_chunk",
                    entity_id=unit_id,
                    metadata={
                        "document_id": row["document_id"],
                        "version_id": row["version_id"],
                        "edge_review_count": len(metadata.get("workflow_edge_reviews") or {}),
                    },
                )
            updated = conn.execute(
                """
                SELECT c.id::text AS unit_id,
                       c.document_id::text AS document_id,
                       c.version_id::text AS version_id,
                       c.chunk_index AS unit_index,
                       c.section,
                       c.heading AS title,
                       c.content,
                       c.metadata,
                       v.document_type,
                       v.review_status,
                       v.extraction_confidence::float AS extraction_confidence
                FROM ai_chunks c
                JOIN ai_document_versions v ON v.id = c.version_id
                WHERE c.id = %s
                """,
                (unit_id,),
            ).fetchone()

    item = dict(updated)
    updated_metadata = item.get("metadata") or {}
    if not isinstance(updated_metadata, dict):
        updated_metadata = {}
    source_type = str(updated_metadata.get("source_type") or "")
    return extraction_unit_from_row(
        item,
        str(item.get("document_type") or ""),
        source_type,
        updated_metadata,
    )


def create_extraction_unit(
    *,
    version_id: str,
    title: str,
    content: str,
    unit_type: str,
    confidence: float,
    review_status: str,
    metadata: dict[str, Any],
    actor: str,
    embedding: list[float],
) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            version = conn.execute(
                """
                SELECT v.id::text AS version_id,
                       v.document_id::text AS document_id,
                       v.status AS version_status,
                       v.document_type,
                       v.review_status,
                       v.extraction_confidence::float AS extraction_confidence
                FROM ai_document_versions v
                WHERE v.id = %s
                FOR UPDATE
                """,
                (version_id,),
            ).fetchone()
            if not version:
                raise LookupError("document_version_not_found")
            if version["version_status"] != "draft":
                raise ValueError("published_or_archived_versions_are_immutable")

            next_index = conn.execute(
                "SELECT COALESCE(MAX(chunk_index), -1) + 1 AS next_index FROM ai_chunks WHERE version_id = %s",
                (version_id,),
            ).fetchone()["next_index"]
            unit_id = str(uuid.uuid4())
            merged_metadata = {
                **(metadata or {}),
                "unit_type": unit_type,
                "confidence": confidence,
                "review_status": review_status,
                "reviewed_by": actor,
                "manual_curation_status": "created_stub",
                "source_evidence_only": True,
                "publish_blocked": True,
                "publish_blocked_reason": "manual_review_required",
            }
            conn.execute(
                """
                INSERT INTO ai_chunks (
                  id, document_id, version_id, chunk_index, section, heading, content,
                  token_count, embedding, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
                """,
                (
                    unit_id,
                    version["document_id"],
                    version_id,
                    next_index,
                    pg_text(unit_type),
                    pg_text(title),
                    pg_text(content),
                    len(tokenize(content)),
                    vector_literal(embedding),
                    pg_text(json.dumps(merged_metadata)),
                ),
            )
            conn.execute(
                """
                UPDATE ai_document_versions
                SET review_status = CASE
                    WHEN review_status = 'approved' THEN review_status
                    ELSE 'reviewed'
                END,
                    chunk_count = (SELECT COUNT(*) FROM ai_chunks WHERE version_id = %s)
                WHERE id = %s
                """,
                (version_id, version_id),
            )
            conn.execute(
                "UPDATE ai_documents SET updated_at = now() WHERE id = %s",
                (version["document_id"],),
            )
            audit_tx(
                conn,
                actor=actor,
                action="extraction_unit_create",
                entity_type="ai_chunk",
                entity_id=unit_id,
                metadata={
                    "document_id": version["document_id"],
                    "version_id": version_id,
                    "unit_type": unit_type,
                    "review_status": review_status,
                },
            )
            created = conn.execute(
                """
                SELECT c.id::text AS unit_id,
                       c.document_id::text AS document_id,
                       c.version_id::text AS version_id,
                       c.chunk_index AS unit_index,
                       c.section,
                       c.heading AS title,
                       c.content,
                       c.metadata,
                       v.document_type,
                       v.review_status,
                       v.extraction_confidence::float AS extraction_confidence
                FROM ai_chunks c
                JOIN ai_document_versions v ON v.id = c.version_id
                WHERE c.id = %s
                """,
                (unit_id,),
            ).fetchone()

    item = dict(created)
    created_metadata = item.get("metadata") or {}
    if not isinstance(created_metadata, dict):
        created_metadata = {}
    source_type = str(created_metadata.get("source_type") or "")
    return extraction_unit_from_row(
        item,
        str(item.get("document_type") or ""),
        source_type,
        created_metadata,
    )


def version_raw_text(version_id: str) -> dict[str, Any]:
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            SELECT v.id::text AS version_id,
                   v.document_id::text AS document_id,
                   d.title,
                   v.version_number,
                   v.status,
                   v.raw_text,
                   v.chunk_count,
                   v.created_at
            FROM ai_document_versions v
            JOIN ai_documents d ON d.id = v.document_id
            WHERE v.id = %s
            """,
            (version_id,),
        ).fetchone()
        if not row:
            raise LookupError("version_not_found")
        return dict(row)


def version_source_page_image(version_id: str, page_number: int) -> bytes:
    if page_number < 1:
        raise ValueError("page_number_must_be_positive")
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            SELECT source_filename, content_type, raw_data
            FROM ai_document_sources
            WHERE version_id = %s
            """,
            (version_id,),
        ).fetchone()
        if not row:
            raise LookupError("source_file_not_found")
        filename = str(row["source_filename"] or "").lower()
        content_type = str(row["content_type"] or "").lower()
        if not filename.endswith(".pdf") and content_type != "application/pdf":
            raise ValueError("source_preview_only_supports_pdf")
        return render_pdf_page_jpeg(bytes(row["raw_data"]), page_number)


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
    return "und"


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
    normalized_like = f"%{normalize_phrase(query)}%"
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
                   (
                     ts_rank_cd(
                       to_tsvector(
                         'simple',
                         immutable_unaccent(
                           concat_ws(' ', c.heading, c.section, c.metadata->>'sheet_name', c.content)
                         )
                       ),
                       to_tsquery('simple', %s)
                     )
                     + CASE WHEN immutable_unaccent(lower(COALESCE(c.metadata->>'sheet_name', ''))) LIKE %s THEN 1.2 ELSE 0 END
                     + CASE WHEN immutable_unaccent(lower(COALESCE(c.heading, ''))) LIKE %s THEN 0.8 ELSE 0 END
                   ) AS score
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE {where_sql}
              AND to_tsvector(
                    'simple',
                    immutable_unaccent(concat_ws(' ', c.heading, c.section, c.metadata->>'sheet_name', c.content))
                  ) @@ to_tsquery('simple', %s)
            ORDER BY score DESC, v.published_at DESC NULLS LAST
            LIMIT %s
            """,
            [tsquery, normalized_like, normalized_like, *params, tsquery, limit],
        ).fetchall()
        return rerank_structural_matches(query, [dict(row) for row in rows])


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
        clauses.append("COALESCE(c.metadata->>'review_status', '') = 'approved'")
        clauses.append("COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)")
        params.append(["structured", "manually_curated"])
        clauses.append("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'")

    if filters.document_ids:
        clauses.append("c.document_id = ANY(%s)")
        params.append(filters.document_ids)
    if filters.audience:
        clauses.append("((d.metadata->'audience') ?| %s OR (c.metadata->'audience') ?| %s)")
        params.append(filters.audience)
        params.append(filters.audience)
    if filters.tags:
        clauses.append("((d.metadata->'tags') ?| %s OR (c.metadata->'tags') ?| %s)")
        params.append(filters.tags)
        params.append(filters.tags)
    if filters.case_reasons:
        clauses.append("((d.metadata->'case_reasons') ?| %s OR (c.metadata->'case_reasons') ?| %s)")
        params.append(filters.case_reasons)
        params.append(filters.case_reasons)
    if filters.vertical:
        clauses.append("(d.metadata->>'vertical' = ANY(%s) OR c.metadata->>'vertical' = ANY(%s))")
        params.append(filters.vertical)
        params.append(filters.vertical)
    if filters.category:
        clauses.append("(d.metadata->>'category' = ANY(%s) OR c.metadata->>'category' = ANY(%s))")
        params.append(filters.category)
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


def log_chat(response: Any) -> None:
    source_chunk_ids = [citation.chunk_id for citation in response.citations]
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_chat_events (
              id, question, answer, citation_count, confidence, warnings, source_chunk_ids, latency_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            """,
            (
                str(uuid.uuid4()),
                pg_text(response.question),
                pg_text(response.answer),
                len(response.citations),
                response.confidence,
                pg_text(json.dumps(response.warnings, ensure_ascii=False)),
                pg_text(json.dumps(source_chunk_ids, ensure_ascii=False)),
                response.latency_ms,
            ),
        )


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
