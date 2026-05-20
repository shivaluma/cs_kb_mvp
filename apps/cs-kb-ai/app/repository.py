from __future__ import annotations

import json
import math
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from psycopg import Connection, sql
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import ConnectionPool

from app.config import settings
from app.embedding import vector_literal
from app.search_labels import is_bad_search_label, meaningful_search_label
from app.schemas import DocumentMetadata, RetrievalFilters, SynonymGroupCreateRequest, SynonymSuggestionAcceptRequest
from app.text_processing import normalize_phrase, render_pdf_page_jpeg, tokenize


pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
_synonym_cache: tuple[float, list[dict[str, Any]]] = (0, [])
SYNONYM_CACHE_SECONDS = 30
EFFECTIVE_HEADING_SQL = """
CASE
  WHEN COALESCE(c.heading, '') ~ '^[[:space:]]*([Bb][uư][oơ]?c[[:space:]]*)?[0-9]{1,3}(\\.[0-9]{1,3})*\\.?[[:space:]]*$' THEN ''
  WHEN length(trim(COALESCE(c.heading, ''))) > 7
       AND immutable_unaccent(lower(COALESCE(c.content, ''))) LIKE immutable_unaccent(lower(trim(COALESCE(c.heading, '')))) || '%%' THEN ''
  WHEN immutable_unaccent(lower(trim(COALESCE(c.heading, '')))) IN ('yes', 'no', 'start', 'end', 'row', 'dong', 'link') THEN ''
  ELSE COALESCE(c.heading, '')
END
"""
RELATION_TYPES = (
    "references",
    "requires",
    "must_follow",
    "routes_to",
    "escalates_to",
    "uses_macro",
    "uses_tool",
    "has_action_template",
    "has_case_reason",
    "exception_of",
    "supersedes",
    "child_of",
    "parent_of",
    "modifies",
    "related_to",
    "possible_conflict",
)
RELATION_STATUSES = ("suggested", "unresolved", "approved", "rejected", "archived")
RELATION_TYPE_SQL = ", ".join(f"'{relation_type}'" for relation_type in RELATION_TYPES)
BLOCKING_RELATION_TYPES = {"requires", "must_follow", "exception_of", "supersedes"}
URL_RE = re.compile(r"(?:https?://|www\.)[^\s)]+", re.IGNORECASE)
RELATION_TITLE_STOP_RE = re.compile(
    r"\s+(?:trước khi|truoc khi|sau khi|nếu|neu|trong vòng|trong vong|sau đó|sau do|để|de)\b",
    re.IGNORECASE,
)
RELATION_TYPE_PRIORITY = {
    "must_follow": 0,
    "requires": 1,
    "exception_of": 2,
    "supersedes": 3,
    "routes_to": 4,
    "escalates_to": 5,
    "uses_macro": 6,
    "uses_tool": 7,
    "has_action_template": 8,
    "has_case_reason": 9,
    "references": 10,
    "child_of": 11,
    "parent_of": 12,
    "modifies": 13,
    "related_to": 14,
    "possible_conflict": 15,
}
TEXT_RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(
            r"(?:thực hiện|thuc hien|áp dụng|ap dung|xử lý|xu ly|hỗ trợ|ho tro)\s+theo\s+(?P<title>(?:quy\s*(?:định|dinh|trình|trinh)|sop|hướng\s*dẫn|huong\s*dan|macro)[^.;\n]{3,180})",
            re.IGNORECASE,
        ),
        "requires",
        "explicit_text_reference",
    ),
    (
        re.compile(
            r"(?:theo|xem(?:\s+thêm)?|tham\s*khảo|tham\s*khao)\s+(?P<title>(?:quy\s*(?:định|dinh|trình|trinh)|sop|hướng\s*dẫn|huong\s*dan|macro)[^.;\n]{3,180})",
            re.IGNORECASE,
        ),
        "references",
        "explicit_text_reference",
    ),
    (
        re.compile(
            r"(?:chuyển|chuyen)\s+(?:case\s+)?(?:cho|đến|den|về|ve|vào|vao)\s+(?P<title>[A-Za-zÀ-ỹ0-9 _./-]{2,90})",
            re.IGNORECASE,
        ),
        "routes_to",
        "operational_handoff",
    ),
)

DEFAULT_KB_COLLECTIONS = (
    ("cs-core-operating-rules", "CS Core Operating Rules", "domain"),
    ("customer-rider-operations", "Customer / Rider Operations", "audience"),
    ("driver-operations", "Driver Operations", "audience"),
    ("merchant-mcu-operations", "Merchant / MCU Operations", "audience"),
    ("cleaner-operations", "Cleaner Operations", "audience"),
    ("payment-refund", "Payment & Refund", "task"),
    ("account-verification", "Account & Verification", "task"),
    ("trip-order-issues", "Trip / Order Issues", "task"),
    ("promotion-voucher", "Promotion / Voucher", "task"),
    ("social-call-email-handling", "Social / Call / Email Handling", "channel"),
    ("tech-bpla-msc-handoff", "Tech / BPLA / MSC Handoff", "owner"),
    ("qa-zt-compliance", "QA / ZT / Compliance", "risk"),
    ("vip-customer-handling", "VIP Customer Handling", "risk"),
    ("tool-directory", "Tool Directory", "tool"),
    ("product-updates", "Product Updates", "domain"),
)
ADMIN_RESET_TABLE_GROUPS: dict[str, tuple[str, ...]] = {
    "knowledge_base": (
        "ai_document_sources",
        "ai_document_relations",
        "ai_chunks",
        "ai_document_versions",
        "ai_documents",
        "kb_sop_versions",
        "kb_sops",
    ),
    "extraction": (
        "extraction_stage_outputs",
        "extraction_jobs",
    ),
    "operations": (
        "kb_collection_items",
        "kb_collections",
        "tool_links",
        "action_templates",
    ),
    "chat": (
        "ai_chat_messages",
        "ai_chat_sessions",
    ),
    "telemetry": (
        "ai_retrieval_events",
        "ai_chat_events",
        "ai_audit_events",
        "search_synonym_suggestions",
    ),
}
ADMIN_RESET_PRESERVED_TABLES = (
    "taxonomy_intents",
    "search_synonym_groups",
    "search_synonym_terms",
)
ADMIN_RESET_TABLES = tuple(
    dict.fromkeys(table for tables in ADMIN_RESET_TABLE_GROUPS.values() for table in tables)
)


def pg_text(value: Any) -> str:
    return str(value or "").replace("\x00", "")


def jsonb_text(value: Any) -> str:
    return pg_text(json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False))


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump(mode="json"))
    return str(value)


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
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
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
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS publish_state text NOT NULL DEFAULT 'draft'")
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS indexed_at timestamptz")
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS indexing_error text NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE ai_document_versions ADD COLUMN IF NOT EXISTS published_ready_at timestamptz")
        conn.execute(
            """
            UPDATE ai_document_versions
            SET publish_state = CASE
              WHEN status = 'archived' THEN 'archived'
              WHEN status = 'published' AND publish_state IN ('draft', '') THEN 'published_ready'
              WHEN status = 'draft' AND publish_state IN ('published_ready', 'published_indexing_pending', 'published_indexing_failed', 'publishing') THEN 'draft'
              ELSE publish_state
            END,
                indexed_at = CASE
                  WHEN status = 'published' AND publish_state = 'published_ready' THEN COALESCE(indexed_at, published_at, now())
                  ELSE indexed_at
                END,
                published_ready_at = CASE
                  WHEN status = 'published' AND publish_state = 'published_ready' THEN COALESCE(published_ready_at, published_at, now())
                  ELSE published_ready_at
                END
            """
        )
        conn.execute(
            """
            UPDATE ai_document_versions
            SET indexed_at = COALESCE(indexed_at, published_at, now()),
                published_ready_at = COALESCE(published_ready_at, published_at, now()),
                indexing_error = ''
            WHERE status = 'published' AND publish_state = 'published_ready'
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
            f"""
            CREATE TABLE IF NOT EXISTS ai_document_relations (
              id uuid PRIMARY KEY,
              source_document_id uuid NOT NULL REFERENCES ai_documents(id) ON DELETE CASCADE,
              source_version_id uuid NOT NULL REFERENCES ai_document_versions(id) ON DELETE CASCADE,
              source_chunk_id uuid REFERENCES ai_chunks(id) ON DELETE SET NULL,
              target_title text NOT NULL,
              target_title_normalized text NOT NULL,
              target_document_id uuid REFERENCES ai_documents(id) ON DELETE SET NULL,
              target_version_id uuid REFERENCES ai_document_versions(id) ON DELETE SET NULL,
              relation_type text NOT NULL DEFAULT 'references',
              status text NOT NULL DEFAULT 'unresolved',
              created_by text NOT NULL DEFAULT 'system',
              reviewed_by text,
              reviewed_at timestamptz,
              rejection_reason text NOT NULL DEFAULT '',
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT ai_document_relations_type_check
                CHECK (relation_type IN ({RELATION_TYPE_SQL})),
              CONSTRAINT ai_document_relations_status_check
                CHECK (status IN ('suggested', 'unresolved', 'approved', 'rejected', 'archived')),
              UNIQUE (source_version_id, source_chunk_id, target_title_normalized, relation_type)
            )
            """
        )
        conn.execute(
            """
            ALTER TABLE ai_document_relations
            DROP CONSTRAINT IF EXISTS ai_document_relations_type_check
            """
        )
        conn.execute(
            f"""
            ALTER TABLE ai_document_relations
            ADD CONSTRAINT ai_document_relations_type_check
            CHECK (relation_type IN ({RELATION_TYPE_SQL}))
            """
        )
        conn.execute(
            """
            ALTER TABLE ai_document_relations
            DROP CONSTRAINT IF EXISTS ai_document_relations_status_check
            """
        )
        conn.execute(
            """
            ALTER TABLE ai_document_relations
            ADD CONSTRAINT ai_document_relations_status_check
            CHECK (status IN ('suggested', 'unresolved', 'approved', 'rejected', 'archived'))
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
            CREATE TABLE IF NOT EXISTS ai_chat_sessions (
              id uuid PRIMARY KEY,
              title text NOT NULL DEFAULT 'New chat',
              summary text NOT NULL DEFAULT '',
              model_route text NOT NULL DEFAULT 'simple',
              filters jsonb NOT NULL DEFAULT '{}'::jsonb,
              status text NOT NULL DEFAULT 'active',
              message_count integer NOT NULL DEFAULT 0,
              last_message_at timestamptz,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT ai_chat_sessions_status_check CHECK (status IN ('active', 'archived'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_chat_messages (
              id uuid PRIMARY KEY,
              session_id uuid NOT NULL REFERENCES ai_chat_sessions(id) ON DELETE CASCADE,
              role text NOT NULL,
              content text NOT NULL,
              response_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              source_chunk_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
              token_context_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT ai_chat_messages_role_check CHECK (role IN ('user', 'assistant'))
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
        ensure_kb_index_schema(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_documents_status ON ai_documents(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_versions_status ON ai_document_versions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chunks_document_version ON ai_chunks(document_id, version_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_sources_document ON ai_document_sources(document_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_relations_status ON ai_document_relations(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_relations_source ON ai_document_relations(source_document_id, source_version_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_document_relations_target ON ai_document_relations(target_document_id, target_version_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_status_last ON ai_chat_sessions(status, last_message_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_session_created ON ai_chat_messages(session_id, created_at)")
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


def ensure_kb_index_schema(conn: Connection[Any]) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_collections (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          name text NOT NULL,
          slug text NOT NULL UNIQUE,
          collection_type text NOT NULL DEFAULT 'domain',
          description text NOT NULL DEFAULT '',
          owner_team text,
          status text NOT NULL DEFAULT 'active',
          rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_collection_items (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          collection_id uuid NOT NULL REFERENCES kb_collections(id) ON DELETE CASCADE,
          item_type text NOT NULL,
          item_id uuid NOT NULL,
          source text NOT NULL DEFAULT 'manual',
          confidence numeric,
          status text NOT NULL DEFAULT 'suggested',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (collection_id, item_type, item_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_links (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          name text NOT NULL,
          url text NOT NULL,
          tool_type text NOT NULL DEFAULT 'other',
          description text,
          owner_team text,
          status text NOT NULL DEFAULT 'active',
          source_document_id uuid REFERENCES ai_documents(id) ON DELETE SET NULL,
          source_version_id uuid REFERENCES ai_document_versions(id) ON DELETE SET NULL,
          source_unit_id uuid REFERENCES ai_chunks(id) ON DELETE SET NULL,
          source_ref jsonb,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (url)
        )
        """
    )
    conn.execute("ALTER TABLE tool_links ADD COLUMN IF NOT EXISTS source_version_id uuid REFERENCES ai_document_versions(id) ON DELETE SET NULL")
    conn.execute("ALTER TABLE tool_links ADD COLUMN IF NOT EXISTS source_unit_id uuid REFERENCES ai_chunks(id) ON DELETE SET NULL")
    conn.execute("ALTER TABLE tool_links ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_templates (
          id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
          name text NOT NULL,
          action_type text NOT NULL,
          description text NOT NULL DEFAULT '',
          fields jsonb NOT NULL DEFAULT '{}'::jsonb,
          copy_template text,
          related_tool_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
          source_unit_id uuid REFERENCES ai_chunks(id) ON DELETE SET NULL,
          status text NOT NULL DEFAULT 'draft',
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("ALTER TABLE action_templates ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_collection_items_collection ON kb_collection_items(collection_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_collection_items_item ON kb_collection_items(item_type, item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_links_status ON tool_links(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_action_templates_status ON action_templates(status)")
    for slug, name, collection_type in DEFAULT_KB_COLLECTIONS:
        conn.execute(
            """
            INSERT INTO kb_collections (slug, name, collection_type, description, status, rules)
            VALUES (%s, %s, %s, '', 'active', '{}'::jsonb)
            ON CONFLICT (slug) DO UPDATE SET
              name = EXCLUDED.name,
              collection_type = EXCLUDED.collection_type,
              updated_at = now()
            """,
            (slug, name, collection_type),
        )


def health_check() -> dict[str, Any]:
    start = time.perf_counter()
    with connection() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "healthy",
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "detail": "Postgres and pgvector schema are reachable",
    }


def admin_reset_status() -> dict[str, Any]:
    with connection() as conn:
        row_counts = table_counts_tx(conn, ADMIN_RESET_TABLES)
        return {
            "enabled": settings.admin_reset_enabled,
            "required_confirmation": settings.admin_reset_confirmation,
            "destructive_tables": list(ADMIN_RESET_TABLES),
            "preserved_tables": list(ADMIN_RESET_PRESERVED_TABLES),
            "row_counts": row_counts,
            "group_counts": group_counts(row_counts),
            "embedding_dimensions": settings.embedding_dimensions,
            "embedding_column_dimensions": embedding_column_dimensions_tx(conn, "embedding"),
            "embedding_new_column_dimensions": embedding_column_dimensions_tx(conn, "embedding_new"),
            "warning": (
                ""
                if settings.admin_reset_enabled
                else "Set CS_KB_ENABLE_MAGIC_RESET=true on the AI service to enable destructive resets."
            ),
        }


def reset_application_data(actor: str, reason: str = "") -> dict[str, Any]:
    if settings.embedding_dimensions <= 0:
        raise ValueError("invalid_embedding_dimensions")
    reset_id = str(uuid.uuid4())
    clean_actor = pg_text(actor).strip() or "cs-ops-ui"
    clean_reason = pg_text(reason).strip()
    warnings: list[str] = []
    with connection() as conn:
        with conn.transaction():
            deleted_counts = table_counts_tx(conn, ADMIN_RESET_TABLES)
            existing_tables = existing_tables_tx(conn, ADMIN_RESET_TABLES)
            if existing_tables:
                conn.execute(
                    sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                        sql.SQL(", ").join(sql.Identifier(table) for table in existing_tables)
                    )
                )
            reset_ai_chunk_embedding_schema_tx(conn)
            ensure_kb_index_schema(conn)
            seed_search_taxonomy(conn)
            audit_tx(
                conn,
                actor=clean_actor,
                action="admin_magic_reset",
                entity_type="system",
                entity_id=reset_id,
                metadata={
                    "reason": clean_reason,
                    "deleted_counts": deleted_counts,
                    "embedding_dimensions": settings.embedding_dimensions,
                    "preserved_tables": list(ADMIN_RESET_PRESERVED_TABLES),
                },
            )
    with connection() as conn:
        embedding_dimensions = embedding_column_dimensions_tx(conn, "embedding")
        if embedding_dimensions != settings.embedding_dimensions:
            warnings.append(f"embedding_dimension_mismatch:{embedding_dimensions}:{settings.embedding_dimensions}")
    return {
        "reset_id": reset_id,
        "status": "reset",
        "actor": clean_actor,
        "deleted_counts": deleted_counts,
        "group_counts": group_counts(deleted_counts),
        "preserved_tables": list(ADMIN_RESET_PRESERVED_TABLES),
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_column_dimensions": embedding_dimensions,
        "warnings": warnings,
    }


def table_counts_tx(conn: Connection[Any], table_names: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {table: 0 for table in table_names}
    for table in existing_tables_tx(conn, table_names):
        row = conn.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
        ).fetchone()
        counts[table] = int(row[0] if row else 0)
    return counts


def existing_tables_tx(conn: Connection[Any], table_names: tuple[str, ...]) -> list[str]:
    if not table_names:
        return []
    rows = conn.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY(%s)
        """,
        (list(table_names),),
    ).fetchall()
    existing = {str(row[0]) for row in rows}
    return [table for table in table_names if table in existing]


def group_counts(row_counts: dict[str, int]) -> dict[str, int]:
    return {
        group: sum(int(row_counts.get(table, 0)) for table in tables)
        for group, tables in ADMIN_RESET_TABLE_GROUPS.items()
    }


def reset_ai_chunk_embedding_schema_tx(conn: Connection[Any]) -> None:
    if "ai_chunks" not in existing_tables_tx(conn, ("ai_chunks",)):
        return
    dimension = int(settings.embedding_dimensions)
    conn.execute("DROP INDEX IF EXISTS idx_ai_chunks_embedding_hnsw")
    conn.execute("DROP INDEX IF EXISTS idx_ai_chunks_embedding_new_hnsw")
    conn.execute("ALTER TABLE ai_chunks DROP COLUMN IF EXISTS embedding")
    conn.execute("ALTER TABLE ai_chunks DROP COLUMN IF EXISTS embedding_new")
    conn.execute(f"ALTER TABLE ai_chunks ADD COLUMN embedding vector({dimension}) NOT NULL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def embedding_column_dimensions_tx(conn: Connection[Any], column_name: str) -> int | None:
    if column_name not in {"embedding", "embedding_new"}:
        raise ValueError("invalid_embedding_column")
    row = conn.execute(
        """
        SELECT a.atttypmod
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'ai_chunks'
          AND a.attname = %s
          AND NOT a.attisdropped
        """,
        (column_name,),
    ).fetchone()
    if not row:
        return None
    value = row[0]
    return int(value) if value else None


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
                  created_by, approved_by, effective_from, published_at, publish_state
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), CASE WHEN %s = 'published' THEN now() ELSE NULL END, %s)
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
                    "published_indexing_pending" if status == "published" else "draft",
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
            relation_count = sync_unresolved_relations_tx(
                conn,
                document_id=document_id,
                version_id=version_id,
                actor=clean_created_by,
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
                    "relation_count": relation_count,
                },
            )

    return {
        "document_id": document_id,
        "version_id": version_id,
        "external_id": clean_external_id,
        "title": clean_title,
        "version_number": int(next_version),
        "status": status,
        "publish_state": "published_indexing_pending" if status == "published" else "draft",
        "chunk_count": len(chunks),
        "checksum": checksum,
        "document_type": clean_document_type,
        "review_status": "approved" if status == "published" else clean_review_status,
        "extraction_confidence": extraction_confidence,
        "metadata": metadata.model_dump(),
        "indexed_at": None,
        "indexing_error": "",
        "published_ready_at": None,
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
            relation_count = sync_unresolved_relations_tx(
                conn,
                document_id=document_id,
                version_id=version_id,
                actor=pg_text(actor),
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
                    "relation_count": relation_count,
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


def sync_unresolved_relations_tx(conn: Connection[Any], document_id: str, version_id: str, actor: str) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT c.id::text AS chunk_id,
                   c.section,
                   c.heading,
                   c.content,
                   c.metadata,
                   d.title AS source_title
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            WHERE c.document_id = %s AND c.version_id = %s
            ORDER BY c.chunk_index
            """,
            (document_id, version_id),
        ).fetchall()

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    source_title = str(rows[0]["source_title"] or "") if rows else ""
    source_title_norm = normalize_phrase(source_title)
    for row in rows:
        for candidate in relation_candidates_from_chunk(row, source_title_norm):
            key = (str(row["chunk_id"]), candidate["target_title_normalized"], candidate["relation_type"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

    if not candidates:
        return 0

    insert_rows = [
        relation_insert_row(conn, document_id, version_id, candidate, actor)
        for candidate in candidates
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ai_document_relations (
              id, source_document_id, source_version_id, source_chunk_id,
              target_title, target_title_normalized, target_document_id, target_version_id,
              relation_type, status, created_by, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (source_version_id, source_chunk_id, target_title_normalized, relation_type)
            DO UPDATE SET
              target_title = EXCLUDED.target_title,
              target_document_id = CASE
                WHEN ai_document_relations.status IN ('unresolved', 'suggested') THEN EXCLUDED.target_document_id
                ELSE ai_document_relations.target_document_id
              END,
              target_version_id = CASE
                WHEN ai_document_relations.status IN ('unresolved', 'suggested') THEN EXCLUDED.target_version_id
                ELSE ai_document_relations.target_version_id
              END,
              status = CASE
                WHEN ai_document_relations.status IN ('unresolved', 'suggested') THEN EXCLUDED.status
                ELSE ai_document_relations.status
              END,
              metadata = CASE
                WHEN ai_document_relations.status IN ('unresolved', 'suggested') THEN EXCLUDED.metadata
                ELSE ai_document_relations.metadata
              END,
              updated_at = now()
            """,
            insert_rows,
        )
    return len(candidates)


def relation_insert_row(
    conn: Connection[Any],
    document_id: str,
    version_id: str,
    candidate: dict[str, Any],
    actor: str,
) -> tuple[Any, ...]:
    target_document_id = None
    target_version_id = None
    status = "unresolved"
    metadata = dict(candidate.get("metadata") or {})
    if not metadata.get("needs_clarification"):
        target = exact_relation_target_tx(conn, candidate["target_title_normalized"], document_id)
        if target:
            target_document_id = target["document_id"]
            target_version_id = target["version_id"]
            status = "suggested"
            metadata = {
                **metadata,
                "match_status": "exact_title_candidate",
                "matched_target_title": target.get("title", ""),
            }
        else:
            metadata = {**metadata, "match_status": "no_confident_target"}
    else:
        metadata = {**metadata, "match_status": "needs_clarification"}
    return (
        str(uuid.uuid4()),
        document_id,
        version_id,
        candidate["source_chunk_id"] or None,
        candidate["target_title"],
        candidate["target_title_normalized"],
        target_document_id,
        target_version_id,
        candidate["relation_type"],
        status,
        pg_text(actor or "system"),
        pg_text(json.dumps(metadata)),
    )


def exact_relation_target_tx(conn: Connection[Any], normalized_target_title: str, source_document_id: str) -> dict[str, Any] | None:
    if not normalized_target_title:
        return None
    conn.row_factory = dict_row
    rows = conn.execute(
        """
        SELECT d.id::text AS document_id,
               v.id::text AS version_id,
               d.title,
               d.source_filename
        FROM ai_documents d
        JOIN ai_document_versions v ON v.id = d.current_version_id
        WHERE d.status = 'active'
          AND v.status = 'published'
          AND v.publish_state = 'published_ready'
          AND d.id::text <> %s
        """,
        (source_document_id,),
    ).fetchall()
    matches = [
        dict(row)
        for row in rows
        if normalized_target_title in {
            normalize_phrase(str(row.get("title") or "")),
            normalize_phrase(str(row.get("source_filename") or "").rsplit(".", 1)[0]),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def relation_candidates_from_chunk(row: dict[str, Any], source_title_norm: str) -> list[dict[str, Any]]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    unit_type = str(metadata.get("unit_type") or row.get("section") or "")
    heading = str(row.get("heading") or "")
    content = str(row.get("content") or "")
    source_chunk_id = str(row.get("chunk_id") or "")
    raw_items: list[Any] = []

    for key in ("relations", "related_documents", "related_sops", "related_sop_candidates"):
        value = metadata.get(key)
        if isinstance(value, list):
            raw_items.extend(value)
        elif value:
            raw_items.append(value)

    if metadata.get("target_title") or metadata.get("target_sop_title") or metadata.get("related_title"):
        raw_items.append(
            {
                "target_title": metadata.get("target_title") or metadata.get("target_sop_title") or metadata.get("related_title"),
                "relation_type": metadata.get("relation_type"),
            }
        )

    if unit_type == "related_document":
        raw_items.append(
            {
                "target_title": relation_title_from_text(heading, content),
                "relation_type": metadata.get("relation_type"),
            }
        )
    raw_items.extend(relation_items_from_text(heading, content))

    output: list[dict[str, Any]] = []
    for item in raw_items:
        target_title = relation_target_title(item)
        relation_type = normalize_relation_type(
            item.get("relation_type") if isinstance(item, dict) else metadata.get("relation_type"),
            content,
        )
        normalized_title = normalize_phrase(target_title)
        if not normalized_title or normalized_title == source_title_norm:
            continue
        output.append(
            {
                "source_chunk_id": source_chunk_id,
                "target_title": target_title[:300],
                "target_title_normalized": normalized_title[:300],
                "relation_type": relation_type,
                "metadata": {
                    "source_unit_type": unit_type,
                    "source_heading": heading,
                    "source_section": str(row.get("section") or ""),
                    **(item if isinstance(item, dict) else {}),
                },
            }
        )
    return output


def relation_items_from_text(heading: str, content: str) -> list[dict[str, Any]]:
    text = "\n".join([heading, content]).strip()
    if not text:
        return []
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for pattern, relation_type, relation_source in TEXT_RELATION_PATTERNS:
        for match in pattern.finditer(text):
            target_title = clean_relation_title(match.group("title"))
            if not target_title:
                continue
            evidence_text = clean_relation_title(match.group(0))
            needs_clarification = normalize_phrase(target_title) in {
                "quy trinh tuong ung",
                "quy dinh tuong ung",
                "sop tuong ung",
                "quy trinh lien quan",
            }
            key = (normalize_phrase(target_title), relation_type, evidence_text)
            if key in seen:
                continue
            seen.add(key)
            output.append(
                {
                    "target_title": target_title,
                    "relation_type": relation_type,
                    "relation_source": relation_source,
                    "evidence_text": evidence_text[:500],
                    "confidence": 0.86 if not needs_clarification else 0.45,
                    "needs_clarification": needs_clarification,
                }
            )
    for url in URL_RE.findall(text):
        evidence_title = relation_title_near_url(text, url) or relation_title_from_text(heading, content)
        if not evidence_title:
            evidence_title = url
        key = (normalize_phrase(evidence_title), "references", url)
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "target_title": evidence_title,
                "relation_type": "references",
                "relation_source": "explicit_url",
                "target_url": url,
                "evidence_text": url,
                "confidence": 0.8,
            }
        )
    return consolidate_relation_items(output)


def consolidate_relation_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_target: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for item in items:
        normalized_title = normalize_phrase(relation_target_title(item))
        if not normalized_title:
            continue
        current = by_target.get(normalized_title)
        if current is None:
            by_target[normalized_title] = item
            ordered_keys.append(normalized_title)
            continue
        current_type = str(current.get("relation_type") or "references")
        next_type = str(item.get("relation_type") or "references")
        current_priority = RELATION_TYPE_PRIORITY.get(current_type, 99)
        next_priority = RELATION_TYPE_PRIORITY.get(next_type, 99)
        if next_priority < current_priority:
            merged = {**current, **item}
        else:
            merged = {**item, **current}
        if item.get("target_url") and not merged.get("target_url"):
            merged["target_url"] = item["target_url"]
        if item.get("evidence_text") and item["evidence_text"] != merged.get("evidence_text"):
            merged["evidence_text"] = "; ".join(
                value
                for value in [str(merged.get("evidence_text") or ""), str(item.get("evidence_text") or "")]
                if value
            )[:500]
        merged["confidence"] = max(float(current.get("confidence") or 0), float(item.get("confidence") or 0))
        merged["needs_clarification"] = bool(current.get("needs_clarification") or item.get("needs_clarification"))
        by_target[normalized_title] = merged
    return [by_target[key] for key in ordered_keys]


def relation_title_near_url(text: str, url: str) -> str:
    for line in text.splitlines():
        if url not in line:
            continue
        before_url = line.split(url, 1)[0]
        if "(" in before_url:
            before_url = before_url.rsplit("(", 1)[0]
        if ":" in before_url:
            before_url = before_url.rsplit(":", 1)[-1]
        title = clean_relation_title(before_url)
        if title and normalize_phrase(title) not in {"link", "url", "link quy dinh", "source url"}:
            return title
    return ""


def relation_target_title(item: Any) -> str:
    if isinstance(item, str):
        return clean_relation_title(item)
    if isinstance(item, dict):
        for key in ("target_title", "target_sop_title", "title", "label", "document_title", "sop_title", "name"):
            value = clean_relation_title(str(item.get(key) or ""))
            if value:
                return value
    return ""


def relation_title_from_text(heading: str, content: str) -> str:
    for value in (heading, *content.splitlines()):
        cleaned = clean_relation_title(value)
        if cleaned and normalize_phrase(cleaned) not in {"related document", "related sop", "tai lieu lien quan", "sop lien quan"}:
            return cleaned
    return clean_relation_title(content)


def clean_relation_title(value: str) -> str:
    cleaned = " ".join(str(value or "").replace(":", " ").split()).strip(" -•")
    cleaned = RELATION_TITLE_STOP_RE.split(cleaned, maxsplit=1)[0].strip(" -•")
    if len(cleaned) > 300:
        cleaned = cleaned[:300].rsplit(" ", 1)[0].strip()
    return cleaned


def normalize_relation_type(value: Any, content: str = "") -> str:
    normalized = normalize_phrase(str(value or ""))
    if normalized in {"must_follow", "must follow", "bat buoc lam theo", "phai lam theo"}:
        return "must_follow"
    if normalized in {"requires", "require", "required", "dependency", "depends_on", "prerequisite"}:
        return "requires"
    if normalized in {"references", "reference", "links_to"}:
        return "references"
    if normalized in {"related_to", "related to", "related", "lien quan", "lien quan den"}:
        return "related_to"
    if normalized in {"routes_to", "route", "handoff", "handoff_to", "chuyen", "chuyen_cho"}:
        return "routes_to"
    if normalized in {"escalates_to", "escalation", "escalate"}:
        return "escalates_to"
    if normalized in {"uses_macro", "uses macro", "macro", "macro_script", "macro script", "script"}:
        return "uses_macro"
    if normalized in {"uses_tool", "uses tool", "tool", "tool_link", "tool link", "cong cu", "he thong"}:
        return "uses_tool"
    if normalized in {"has_action_template", "action_template", "action template", "quick_action", "quick action"}:
        return "has_action_template"
    if normalized in {"has_case_reason", "case_reason", "case reason", "ly do case"}:
        return "has_case_reason"
    if normalized in {"exception_of", "exception"}:
        return "exception_of"
    if normalized in {"supersedes", "replace", "replaces"}:
        return "supersedes"
    if normalized in {"child_of", "child of", "belongs_to", "belongs to"}:
        return "child_of"
    if normalized in {"parent_of", "parent of", "contains"}:
        return "parent_of"
    if normalized in {"modifies", "modify", "updates", "update"}:
        return "modifies"
    if normalized in {"possible_conflict", "possible conflict", "conflict", "conflicts", "mau thuan", "xung dot"}:
        return "possible_conflict"
    content_norm = normalize_phrase(content)
    if any(signal in content_norm for signal in ["bat buoc", "phai mo", "phai xem", "requires", "must use", "prerequisite"]):
        return "requires"
    if any(signal in content_norm for signal in ["chuyen case", "chuyen cho", "handoff"]):
        return "routes_to"
    return "references"


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
        conn.row_factory = dict_row
        version_row = conn.execute(
            """
            SELECT status,
                   publish_state,
                   COALESCE(indexing_error, '') AS indexing_error
            FROM ai_document_versions
            WHERE id = %s
            """,
            (version_id,),
        ).fetchone()
        if not version_row:
            raise LookupError("version_not_found")
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
                "publish_state": version_row["publish_state"],
                "index_visibility_ready": version_row["status"] == "published" and version_row["publish_state"] == "published_ready",
                "retryable_indexing_failure": version_row["publish_state"] == "published_indexing_failed",
                "indexing_error": version_row["indexing_error"],
            }
        return {
            "ready": True,
            "failure_count": 0,
            "failures": [],
            "publish_state": version_row["publish_state"],
            "index_visibility_ready": version_row["status"] == "published" and version_row["publish_state"] == "published_ready",
            "retryable_indexing_failure": version_row["publish_state"] == "published_indexing_failed",
            "indexing_error": version_row["indexing_error"],
        }


def has_required_source_ref(document_type: str, metadata: dict[str, Any]) -> bool:
    refs = metadata.get("source_refs")
    if not isinstance(refs, list):
        refs = []
    if document_type == "policy_table":
        return bool(metadata.get("source_sheet")) or any(
            isinstance(ref, dict)
            and (
                ref.get("sheet")
                or (ref.get("source_type") == "docx_table" and ref.get("table_index") is not None and ref.get("row_index") is not None)
                or (ref.get("table_index") is not None and ref.get("row_index") is not None)
            )
            for ref in refs
        )
    if document_type == "kb_index_workbook":
        return any(isinstance(ref, dict) and ref.get("sheet") and (ref.get("row_start") or ref.get("row_end")) for ref in refs)
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


REVIEW_FREQUENCIES = {"quarterly", "semiannual", "annual"}


def effective_metadata_value(unit_metadata: dict[str, Any], document_metadata: dict[str, Any], key: str) -> str:
    value = unit_metadata.get(key)
    if value in (None, ""):
        value = document_metadata.get(key)
    return str(value or "").strip()


def high_risk_governance_failures(
    unit_metadata: dict[str, Any],
    document_metadata: dict[str, Any],
    normalized_text: str,
    document_type: str,
) -> list[str]:
    document_type_high_risk = document_type in {"policy_rule", "policy_table", "workflow_diagram"}
    document_text = normalize_phrase(json.dumps(document_metadata, ensure_ascii=False))
    is_high_risk = (
        document_type_high_risk
        or is_high_risk_metadata(document_metadata, document_text)
        or is_high_risk_metadata(unit_metadata, normalized_text)
    )
    if not is_high_risk:
        return []

    failures: list[str] = []
    if not effective_metadata_value(unit_metadata, document_metadata, "risk_level"):
        failures.append("missing_risk_level")
    if not effective_metadata_value(unit_metadata, document_metadata, "owner_team"):
        failures.append("missing_owner_team")
    review_frequency = normalize_phrase(effective_metadata_value(unit_metadata, document_metadata, "review_frequency")).replace(" ", "_")
    if review_frequency not in REVIEW_FREQUENCIES:
        failures.append("missing_review_frequency")
    if not parse_metadata_date(effective_metadata_value(unit_metadata, document_metadata, "last_reviewed_at")):
        failures.append("missing_last_reviewed_at")
    next_review_due = parse_metadata_date(effective_metadata_value(unit_metadata, document_metadata, "next_review_due"))
    if not next_review_due:
        failures.append("missing_next_review_due")
    elif next_review_due < datetime.now(timezone.utc).date():
        failures.append("high_risk_review_due_in_past")
    return failures


def parse_metadata_date(value: str) -> Any:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text.split("T", 1)[0], "%Y-%m-%d").date()
        except ValueError:
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
    governance_failures: list[str] = []
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        review_status = str(metadata.get("review_status") or "needs_review")
        if review_status == "rejected":
            continue
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
        governance_failures.extend(high_risk_governance_failures(metadata, document_metadata, text, version["document_type"]))
        if unit_type:
            workflow_unit_status_by_type[unit_type] = workflow_unit_status_by_type.get(unit_type, False) or is_reviewed_status(metadata.get("review_status"))
        required_unit_types.update(required_unit_types_from_metadata(metadata))
        has_full_sop = has_full_sop or unit_type == "full_sop" or retrieval_scope == "document"
        pending_units += 1 if review_status == "needs_review" else 0
        has_owner = has_owner or bool(metadata.get("owner_team"))
        has_effective_from = has_effective_from or bool(metadata.get("effective_from"))
        has_historical_sheets = has_historical_sheets or bool(metadata.get("historical_sheets"))
        has_high_risk_signal = has_high_risk_signal or is_high_risk_metadata(metadata, text)
        if unit_type == "workflow_graph" or metadata.get("workflow_graph"):
            has_workflow_graph = True
            workflow_graph_reviewed = review_status in {"reviewed", "approved"}
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
    if version["document_type"] in {"policy_table", "policy_rule", "workflow_diagram", "kb_index_workbook"} and atomic_units == 0:
        failures.append("missing_production_atomic_units")
    if degraded_unconverted:
        failures.append(f"{degraded_unconverted}_degraded_units_need_manual_curation")
    if pending_units:
        failures.append(f"{pending_units}_units_need_review")
    if not has_owner:
        failures.append("missing_owner_team")
    failures.extend(governance_failures)
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
    high_risk_publish_scope = version["document_type"] in {"policy_rule", "policy_table", "workflow_diagram", "kb_index_workbook"} or has_high_risk_signal
    failures.extend(unresolved_relation_publish_gate_failures_tx(conn, version_id, high_risk_publish_scope))

    failures = list(dict.fromkeys(failures))
    if failures:
        raise ValueError("publish_readiness_failed:" + ",".join(failures))


def unresolved_relation_publish_gate_failures_tx(conn: Connection[Any], version_id: str, high_risk_publish_scope: bool) -> list[str]:
    if not high_risk_publish_scope:
        return []
    conn.row_factory = dict_row
    rows = conn.execute(
        """
        SELECT id::text AS id
        FROM ai_document_relations
        WHERE source_version_id = %s
          AND status IN ('unresolved', 'suggested')
          AND (
            relation_type = ANY(%s)
            OR COALESCE(metadata->>'affects_publish_gate', 'false') = 'true'
          )
        """,
        (version_id, sorted(BLOCKING_RELATION_TYPES)),
    ).fetchall()
    if not rows:
        return []
    return [f"{len(rows)}_unresolved_required_relations"]


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
        SET publish_state = 'publishing',
            indexing_error = ''
        WHERE id = %s
        """,
        (version_id,),
    )
    audit_tx(
        conn,
        actor=actor,
        action="version_publishing_started",
        entity_type="ai_document_version",
        entity_id=version_id,
        metadata={"document_id": str(row["document_id"]), "force": force, "version_number": row["version_number"]},
    )

    previous_versions = conn.execute(
        """
        SELECT id::text AS version_id, version_number
        FROM ai_document_versions
        WHERE document_id = %s AND status = 'published' AND id <> %s
        """,
        (row["document_id"], version_id),
    ).fetchall()
    conn.execute(
        """
        UPDATE ai_document_versions
        SET status = 'archived',
            publish_state = 'archived',
            archived_at = now()
        WHERE document_id = %s AND status = 'published' AND id <> %s
        """,
        (row["document_id"], version_id),
    )
    for previous in previous_versions:
        audit_tx(
            conn,
            actor=actor,
            action="previous_version_archived",
            entity_type="ai_document_version",
            entity_id=str(previous["version_id"]),
            metadata={"document_id": str(row["document_id"]), "published_version_id": version_id, "version_number": previous["version_number"]},
        )
    conn.execute(
        """
        UPDATE ai_document_versions
        SET status = 'published',
            publish_state = 'published_indexing_pending',
            review_status = 'approved',
            approved_by = %s,
            published_at = COALESCE(published_at, now()),
            indexed_at = NULL,
            indexing_error = '',
            published_ready_at = NULL,
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
               v.publish_state,
               v.checksum,
               v.chunk_count,
               v.document_type,
               v.review_status,
               v.extraction_confidence::float AS extraction_confidence,
               v.indexed_at,
               COALESCE(v.indexing_error, '') AS indexing_error,
               v.published_ready_at,
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
    if published["document_type"] == "kb_index_workbook":
        materialize_kb_index_version_tx(conn, str(published["document_id"]), version_id, actor)
    else:
        materialize_collection_items_for_version_tx(conn, str(published["document_id"]), version_id, actor, source="manual")
    audit_tx(
        conn,
        actor=actor,
        action="version_published",
        entity_type="ai_document_version",
        entity_id=version_id,
        metadata={"document_id": str(published["document_id"]), "version_number": published["version_number"], "publish_state": "published_indexing_pending"},
    )
    audit_tx(
        conn,
        actor=actor,
        action="publish_version",
        entity_type="ai_document_version",
        entity_id=version_id,
        metadata={"document_id": str(published["document_id"]), "version_number": published["version_number"], "publish_state": "published_indexing_pending"},
    )
    return dict(published)


def prepare_version_indexing_retry(version_id: str, actor: str = "api-gateway") -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = publish_payload_for_version_tx(conn, version_id, for_update=True)
            if not row:
                raise LookupError("version_not_found")
            if row["status"] != "published":
                raise ValueError("version_not_published")
            conn.execute(
                """
                UPDATE ai_document_versions
                SET publish_state = 'published_indexing_pending',
                    indexing_error = '',
                    indexed_at = NULL,
                    published_ready_at = NULL
                WHERE id = %s
                """,
                (version_id,),
            )
            audit_tx(
                conn,
                actor=actor,
                action="version_indexing_retry_started",
                entity_type="ai_document_version",
                entity_id=version_id,
                metadata={"document_id": str(row["document_id"])},
            )
            return publish_payload_for_version_tx(conn, version_id) or dict(row)


def mark_version_indexing_result(
    version_id: str,
    *,
    actor: str = "api-gateway",
    success: bool,
    lexical_index_synced: bool = False,
    vector_index_verified: bool = False,
    error: str = "",
) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = publish_payload_for_version_tx(conn, version_id, for_update=True)
            if not row:
                raise LookupError("version_not_found")
            if row["status"] != "published":
                raise ValueError("version_not_published")

            chunk_count = conn.execute(
                "SELECT COUNT(*)::int AS chunk_count FROM ai_chunks WHERE version_id = %s",
                (version_id,),
            ).fetchone()["chunk_count"]
            vector_ready = vector_index_verified and chunk_count > 0
            if success and lexical_index_synced and vector_ready:
                conn.execute(
                    """
                    UPDATE ai_document_versions
                    SET publish_state = 'published_ready',
                        indexed_at = now(),
                        published_ready_at = now(),
                        indexing_error = ''
                    WHERE id = %s
                    """,
                    (version_id,),
                )
                audit_tx(
                    conn,
                    actor=actor,
                    action="lexical_index_synced",
                    entity_type="ai_document_version",
                    entity_id=version_id,
                    metadata={"document_id": str(row["document_id"])},
                )
                audit_tx(
                    conn,
                    actor=actor,
                    action="vector_index_verified",
                    entity_type="ai_document_version",
                    entity_id=version_id,
                    metadata={"document_id": str(row["document_id"]), "chunk_count": chunk_count},
                )
                audit_tx(
                    conn,
                    actor=actor,
                    action="version_published_ready",
                    entity_type="ai_document_version",
                    entity_id=version_id,
                    metadata={"document_id": str(row["document_id"])},
                )
            else:
                reason = error or ("vector_index_missing_chunks" if chunk_count <= 0 else "indexing_not_confirmed")
                conn.execute(
                    """
                    UPDATE ai_document_versions
                    SET publish_state = 'published_indexing_failed',
                        indexing_error = %s
                    WHERE id = %s
                    """,
                    (pg_text(reason)[:2000], version_id),
                )
                audit_tx(
                    conn,
                    actor=actor,
                    action="publish_indexing_failed",
                    entity_type="ai_document_version",
                    entity_id=version_id,
                    metadata={"document_id": str(row["document_id"]), "error": reason, "chunk_count": chunk_count},
                )
                audit_tx(
                    conn,
                    actor=actor,
                    action="index_sync_failed",
                    entity_type="ai_document_version",
                    entity_id=version_id,
                    metadata={"document_id": str(row["document_id"]), "error": reason, "chunk_count": chunk_count},
                )
            updated = publish_payload_for_version_tx(conn, version_id)
            if not updated:
                raise LookupError("version_not_found")
            return updated


def publish_payload_for_version_tx(conn: Connection[Any], version_id: str, for_update: bool = False) -> dict[str, Any] | None:
    lock = "FOR UPDATE" if for_update else ""
    row = conn.execute(
        f"""
        SELECT v.id::text AS version_id,
               v.document_id::text AS document_id,
               d.external_id,
               d.title,
               v.version_number,
               v.status,
               v.publish_state,
               v.checksum,
               v.chunk_count,
               v.document_type,
               v.review_status,
               v.extraction_confidence::float AS extraction_confidence,
               v.indexed_at,
               COALESCE(v.indexing_error, '') AS indexing_error,
               v.published_ready_at,
               d.metadata
        FROM ai_document_versions v
        JOIN ai_documents d ON d.id = v.document_id
        WHERE v.id = %s
        {lock}
        """,
        (version_id,),
    ).fetchone()
    return dict(row) if row else None


def archive_document_collection_items_tx(conn: Connection[Any], document_id: str) -> None:
    conn.execute(
        """
        UPDATE kb_collection_items i
        SET status = 'archived',
            updated_at = now()
        FROM ai_chunks ch
        WHERE i.item_type = 'sop_unit'
          AND i.item_id = ch.id
          AND ch.document_id = %s
          AND i.status <> 'archived'
        """,
        (document_id,),
    )


def archive_document_relations_for_document_tx(conn: Connection[Any], document_id: str, actor: str) -> int:
    archived_metadata = {
        "archive_reason": "document_archived",
        "archived_document_id": document_id,
        "archived_by": actor,
    }
    return conn.execute(
        """
        UPDATE ai_document_relations
        SET status = 'archived',
            reviewed_by = %s,
            reviewed_at = now(),
            metadata = metadata || %s::jsonb,
            updated_at = now()
        WHERE status <> 'archived'
          AND (source_document_id = %s OR target_document_id = %s)
        """,
        (pg_text(actor), pg_text(json.dumps(archived_metadata)), document_id, document_id),
    ).rowcount


def materialize_collection_items_for_version_tx(conn: Connection[Any], document_id: str, version_id: str, actor: str, source: str) -> dict[str, int]:
    conn.row_factory = dict_row
    archive_document_collection_items_tx(conn, document_id)
    rows = conn.execute(
        """
        SELECT id::text AS chunk_id,
               metadata
        FROM ai_chunks
        WHERE document_id = %s
          AND version_id = %s
          AND COALESCE(metadata->>'review_status', '') = 'approved'
          AND COALESCE(metadata->>'collection_slug', '') <> ''
        ORDER BY chunk_index
        """,
        (document_id, version_id),
    ).fetchall()
    collections = 0
    collection_items = 0
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        assignment_status = str(metadata.get("collection_assignment_status") or "approved").strip()
        if assignment_status not in {"approved", "reviewed"}:
            continue
        collection_slug = str(metadata.get("collection_slug") or "").strip()
        collection_name = str(metadata.get("collection_name") or collection_slug or "").strip()
        if not collection_slug or not collection_name:
            continue
        collection_id = upsert_kb_collection_tx(
            conn,
            slug=collection_slug,
            name=collection_name,
            collection_type=str(metadata.get("collection_type") or "domain"),
            description=str(metadata.get("collection_description") or ""),
            owner_team=str(metadata.get("owner_team") or ""),
            rules={"source_document_id": document_id, "source_version_id": version_id},
        )
        collections += 1
        link_kb_collection_item_tx(
            conn,
            collection_id=collection_id,
            item_type="sop_unit",
            item_id=str(row["chunk_id"]),
            source=source,
            confidence=float(metadata.get("collection_confidence") or metadata.get("confidence") or 0) if (metadata.get("collection_confidence") is not None or metadata.get("confidence") is not None) else None,
            status="approved",
        )
        collection_items += 1

    if collection_items:
        audit_tx(
            conn,
            actor=actor,
            action="document_collection_items_materialized",
            entity_type="ai_document_version",
            entity_id=version_id,
            metadata={"document_id": document_id, "collections": collections, "collection_items": collection_items, "source": source},
        )
    return {"collections": collections, "collection_items": collection_items}


def materialize_kb_index_version_tx(conn: Connection[Any], document_id: str, version_id: str, actor: str) -> dict[str, int]:
    conn.row_factory = dict_row
    archive_document_collection_items_tx(conn, document_id)
    rows = conn.execute(
        """
        SELECT id::text AS chunk_id,
               heading,
               content,
               metadata
        FROM ai_chunks
        WHERE document_id = %s
          AND version_id = %s
          AND COALESCE(metadata->>'review_status', '') = 'approved'
          AND COALESCE(metadata->>'kb_index', 'false') = 'true'
        ORDER BY chunk_index
        """,
        (document_id, version_id),
    ).fetchall()
    collections = 0
    collection_items = 0
    tools = 0
    actions = 0
    for row in rows:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        collection_slug = str(metadata.get("collection_slug") or "").strip()
        collection_name = str(metadata.get("collection_name") or collection_slug or "").strip()
        if collection_slug and collection_name:
            collection_id = upsert_kb_collection_tx(
                conn,
                slug=collection_slug,
                name=collection_name,
                collection_type=str(metadata.get("collection_type") or "domain"),
                description=str(metadata.get("description") or ""),
                owner_team=str(metadata.get("owner_team") or ""),
                rules={"source_document_id": document_id, "source_version_id": version_id},
            )
            collections += 1
            link_kb_collection_item_tx(
                conn,
                collection_id=collection_id,
                item_type="sop_unit",
                item_id=str(row["chunk_id"]),
                source="imported",
                confidence=float(metadata.get("confidence") or 0) if metadata.get("confidence") is not None else None,
                status="approved",
            )
            collection_items += 1

        unit_type = str(metadata.get("unit_type") or "")
        if unit_type == "tool_link":
            upsert_tool_link_tx(conn, document_id, version_id, row, metadata)
            tools += 1
        if unit_type == "quick_action_rule":
            upsert_action_template_tx(conn, row, metadata)
            actions += 1

    audit_tx(
        conn,
        actor=actor,
        action="kb_index_materialized",
        entity_type="ai_document_version",
        entity_id=version_id,
        metadata={
            "document_id": document_id,
            "collections": collections,
            "collection_items": collection_items,
            "tool_links": tools,
            "action_templates": actions,
        },
    )
    return {"collections": collections, "collection_items": collection_items, "tool_links": tools, "action_templates": actions}


def upsert_kb_collection_tx(
    conn: Connection[Any],
    *,
    slug: str,
    name: str,
    collection_type: str,
    description: str,
    owner_team: str,
    rules: dict[str, Any],
) -> str:
    row = conn.execute(
        """
        INSERT INTO kb_collections (slug, name, collection_type, description, owner_team, status, rules)
        VALUES (%s, %s, %s, %s, NULLIF(%s, ''), 'active', %s::jsonb)
        ON CONFLICT (slug) DO UPDATE SET
          name = EXCLUDED.name,
          collection_type = EXCLUDED.collection_type,
          description = COALESCE(NULLIF(EXCLUDED.description, ''), kb_collections.description),
          owner_team = COALESCE(EXCLUDED.owner_team, kb_collections.owner_team),
          rules = kb_collections.rules || EXCLUDED.rules,
          updated_at = now()
        RETURNING id::text AS id
        """,
        (slug, name, collection_type or "domain", description, owner_team, json.dumps(rules)),
    ).fetchone()
    return str(row["id"])


def link_kb_collection_item_tx(
    conn: Connection[Any],
    *,
    collection_id: str,
    item_type: str,
    item_id: str,
    source: str,
    confidence: float | None,
    status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO kb_collection_items (collection_id, item_type, item_id, source, confidence, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (collection_id, item_type, item_id) DO UPDATE SET
          source = EXCLUDED.source,
          confidence = EXCLUDED.confidence,
          status = EXCLUDED.status,
          updated_at = now()
        """,
        (collection_id, item_type, item_id, source, confidence, status),
    )


def upsert_tool_link_tx(conn: Connection[Any], document_id: str, version_id: str, row: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    url = str(metadata.get("url") or "").strip()
    if not url:
        return None
    source_refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    source_ref = source_refs[0] if source_refs and isinstance(source_refs[0], dict) else {}
    result = conn.execute(
        """
        INSERT INTO tool_links (
          name, url, tool_type, description, owner_team, status,
          source_document_id, source_version_id, source_unit_id, source_ref, metadata
        )
        VALUES (%s, %s, %s, %s, NULLIF(%s, ''), 'active', %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (url) DO UPDATE SET
          name = EXCLUDED.name,
          tool_type = EXCLUDED.tool_type,
          description = EXCLUDED.description,
          owner_team = COALESCE(EXCLUDED.owner_team, tool_links.owner_team),
          status = 'active',
          source_document_id = EXCLUDED.source_document_id,
          source_version_id = EXCLUDED.source_version_id,
          source_unit_id = EXCLUDED.source_unit_id,
          source_ref = EXCLUDED.source_ref,
          metadata = tool_links.metadata || EXCLUDED.metadata,
          updated_at = now()
        RETURNING id::text AS id
        """,
        (
            str(metadata.get("name") or row.get("heading") or "Tool"),
            url,
            str(metadata.get("tool_type") or "other"),
            str(metadata.get("description") or row.get("content") or ""),
            str(metadata.get("owner_team") or ""),
            document_id,
            version_id,
            str(row["chunk_id"]),
            json.dumps(source_ref),
            json.dumps({"source_chunk_id": str(row["chunk_id"]), "collection_slug": metadata.get("collection_slug", "")}),
        ),
    ).fetchone()
    return str(result["id"]) if result else None


def upsert_action_template_tx(conn: Connection[Any], row: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    name = str(metadata.get("name") or row.get("heading") or "").strip()
    action_type = str(metadata.get("action_type") or "").strip()
    if not name or not action_type:
        return None
    existing = conn.execute(
        """
        SELECT id::text AS id
        FROM action_templates
        WHERE source_unit_id = %s
        """,
        (str(row["chunk_id"]),),
    ).fetchone()
    related_tool_ids = [str(item) for item in metadata.get("related_tool_ids", []) if str(item)]
    if existing:
        conn.execute(
            """
            UPDATE action_templates
            SET name = %s,
                action_type = %s,
                description = %s,
                fields = %s::jsonb,
                copy_template = %s,
                related_tool_ids = %s::uuid[],
                status = 'approved',
                metadata = metadata || %s::jsonb,
                updated_at = now()
            WHERE id = %s
            """,
            (
                name,
                action_type,
                str(metadata.get("description") or row.get("content") or ""),
                json.dumps(metadata.get("fields") if isinstance(metadata.get("fields"), dict) else {}),
                str(metadata.get("copy_template") or ""),
                related_tool_ids,
                json.dumps({"collection_slug": metadata.get("collection_slug", "")}),
                existing["id"],
            ),
        )
        return str(existing["id"])
    result = conn.execute(
        """
        INSERT INTO action_templates (
          name, action_type, description, fields, copy_template,
          related_tool_ids, source_unit_id, status, metadata
        )
        VALUES (%s, %s, %s, %s::jsonb, %s, %s::uuid[], %s, 'approved', %s::jsonb)
        RETURNING id::text AS id
        """,
        (
            name,
            action_type,
            str(metadata.get("description") or row.get("content") or ""),
            json.dumps(metadata.get("fields") if isinstance(metadata.get("fields"), dict) else {}),
            str(metadata.get("copy_template") or ""),
            related_tool_ids,
            str(row["chunk_id"]),
            json.dumps({"collection_slug": metadata.get("collection_slug", "")}),
        ),
    ).fetchone()
    return str(result["id"]) if result else None


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
                "UPDATE ai_document_versions SET status = 'archived', publish_state = 'archived', archived_at = now() WHERE document_id = %s",
                (document_id,),
            )
            archive_document_collection_items_tx(conn, document_id)
            archived_relation_count = archive_document_relations_for_document_tx(conn, document_id, actor)
            audit_tx(
                conn,
                actor=actor,
                action="document_archive",
                entity_type="ai_document",
                entity_id=document_id,
                metadata={"archived_relation_count": archived_relation_count},
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
                   v.publish_state AS latest_publish_state,
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


def list_kb_collections() -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT c.id::text AS id,
                   c.name,
                   c.slug,
                   c.collection_type,
                   COALESCE(c.description, '') AS description,
                   COALESCE(c.owner_team, '') AS owner_team,
                   c.status,
                   c.rules,
                   COUNT(i.id)::int AS item_count,
                   COUNT(*) FILTER (
                     WHERE COALESCE(ch.metadata->>'risk_level', '') IN ('high', 'critical')
                   )::int AS high_risk_count,
                   COUNT(DISTINCT r.id) FILTER (
                     WHERE r.status IN ('unresolved', 'suggested')
                   )::int AS unresolved_relation_count,
                   c.created_at,
                   c.updated_at
            FROM kb_collections c
            LEFT JOIN kb_collection_items i ON i.collection_id = c.id AND i.status = 'approved'
            LEFT JOIN ai_chunks ch ON i.item_type = 'sop_unit' AND ch.id = i.item_id
            LEFT JOIN ai_document_relations r ON r.source_chunk_id = ch.id AND r.status IN ('unresolved', 'suggested')
            WHERE c.status = 'active'
            GROUP BY c.id
            ORDER BY c.collection_type, c.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def list_search_filter_options() -> dict[str, list[str]]:
    options: dict[str, set[str]] = {
        "audience": set(),
        "vertical": set(),
        "category": set(),
        "tags": set(),
        "case_reasons": set(),
        "collections": set(),
        "task_types": set(),
        "unit_types": set(),
    }

    def add_values(bucket: str, value: Any) -> None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item or "").strip()
            if text:
                options[bucket].add(text)

    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT d.metadata AS document_metadata,
                   c.metadata AS chunk_metadata,
                   c.section
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE d.status = 'active'
              AND v.status = 'published'
              AND v.publish_state = 'published_ready'
              AND d.current_version_id = v.id
              AND COALESCE(c.metadata->>'review_status', '') = 'approved'
              AND COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)
              AND COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'
            """,
            (["structured", "manually_curated"],),
        ).fetchall()

    for row in rows:
        for metadata in (row["document_metadata"] or {}, row["chunk_metadata"] or {}):
            add_values("audience", metadata.get("audience"))
            add_values("vertical", metadata.get("vertical"))
            add_values("category", metadata.get("category"))
            add_values("tags", metadata.get("tags"))
            add_values("case_reasons", metadata.get("case_reasons"))
            add_values("collections", metadata.get("collection_slug"))
            add_values("task_types", metadata.get("task_type"))
            add_values("unit_types", metadata.get("unit_type"))
        add_values("unit_types", row["section"])

    return {key: sorted(values, key=str.casefold) for key, values in options.items()}


def get_kb_collection(collection_id_or_slug: str) -> dict[str, Any]:
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            SELECT c.id::text AS id,
                   c.name,
                   c.slug,
                   c.collection_type,
                   COALESCE(c.description, '') AS description,
                   COALESCE(c.owner_team, '') AS owner_team,
                   c.status,
                   c.rules,
                   COUNT(i.id)::int AS item_count,
                   COUNT(*) FILTER (
                     WHERE COALESCE(ch.metadata->>'risk_level', '') IN ('high', 'critical')
                   )::int AS high_risk_count,
                   COUNT(DISTINCT r.id) FILTER (
                     WHERE r.status IN ('unresolved', 'suggested')
                   )::int AS unresolved_relation_count,
                   c.created_at,
                   c.updated_at
            FROM kb_collections c
            LEFT JOIN kb_collection_items i ON i.collection_id = c.id AND i.status = 'approved'
            LEFT JOIN ai_chunks ch ON i.item_type = 'sop_unit' AND ch.id = i.item_id
            LEFT JOIN ai_document_relations r ON r.source_chunk_id = ch.id AND r.status IN ('unresolved', 'suggested')
            WHERE c.id::text = %s OR c.slug = %s
            GROUP BY c.id
            """,
            (collection_id_or_slug, collection_id_or_slug),
        ).fetchone()
        if not row:
            raise LookupError("collection_not_found")
        collection = dict(row)
        collection["items"] = collection_items_tx(conn, collection["id"])
        collection["issue_router_units"] = list_issue_router(collection=collection["slug"], limit=100)
        collection["tools"] = list_tool_links(collection=collection["slug"])
        collection["action_templates"] = list_action_templates(collection=collection["slug"])
        collection["relations"] = list_document_relations_for_collection_tx(conn, collection["slug"])
        return collection


def collection_items_tx(conn: Connection[Any], collection_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.id::text AS id,
               i.item_type,
               i.item_id::text AS item_id,
               i.source,
               i.confidence::float AS confidence,
               i.status,
               ch.heading,
               ch.section,
               ch.metadata,
               d.title AS document_title
        FROM kb_collection_items i
        LEFT JOIN ai_chunks ch ON i.item_type = 'sop_unit' AND ch.id = i.item_id
        LEFT JOIN ai_documents d ON d.id = ch.document_id
        WHERE i.collection_id = %s
          AND i.status = 'approved'
        ORDER BY i.updated_at DESC
        """,
        (collection_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_document_relations_for_collection_tx(conn: Connection[Any], collection_slug: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.id::text AS id,
               r.source_document_id::text AS source_document_id,
               r.source_version_id::text AS source_version_id,
               r.source_chunk_id::text AS source_chunk_id,
               r.target_title,
               r.relation_type,
               r.status,
               r.metadata,
               r.created_at,
               r.updated_at
        FROM ai_document_relations r
        JOIN ai_chunks ch ON ch.id = r.source_chunk_id
        WHERE ch.metadata->>'collection_slug' = %s
        ORDER BY r.updated_at DESC
        """,
        (collection_slug,),
    ).fetchall()
    return [dict(row) for row in rows]


def unresolved_relations_for_chunks(chunk_ids: list[str]) -> list[dict[str, Any]]:
    ids = [item for item in dict.fromkeys(chunk_ids) if item]
    if not ids:
        return []
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   source_chunk_id::text AS source_chunk_id,
                   target_title,
                   relation_type,
                   status,
                   metadata
            FROM ai_document_relations
            WHERE source_chunk_id::text = ANY(%s)
              AND status IN ('unresolved', 'suggested')
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            (ids,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_issue_router(
    query: str = "",
    audience: list[str] | None = None,
    vertical: list[str] | None = None,
    collection: str = "",
    task_type: list[str] | None = None,
    risk_level: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    effective_heading = EFFECTIVE_HEADING_SQL
    clauses = [
        "d.status = 'active'",
        "v.status = 'published'",
        "v.publish_state = 'published_ready'",
        "d.current_version_id = v.id",
        "COALESCE(c.metadata->>'review_status', '') = 'approved'",
        "COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)",
        "COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'",
        "COALESCE(c.metadata->>'unit_type', '') = ANY(%s)",
    ]
    params: list[Any] = [["structured", "manually_curated"], ["issue_router_unit", "vip_overlay_rule", "product_update_note"]]
    if query:
        clauses.append(f"immutable_unaccent(lower(concat_ws(' ', {effective_heading}, c.content, c.metadata::text))) LIKE immutable_unaccent(lower(%s))")
        params.append(f"%{query}%")
    if audience:
        clauses.append("(c.metadata->'audience') ?| %s")
        params.append(audience)
    if vertical:
        clauses.append("(c.metadata->'vertical') ?| %s")
        params.append(vertical)
    if collection:
        clauses.append("c.metadata->>'collection_slug' = %s")
        params.append(collection)
    if task_type:
        clauses.append("(c.metadata->'task_type') ?| %s")
        params.append(task_type)
    if risk_level:
        clauses.append("COALESCE(c.metadata->>'risk_level', '') = %s")
        params.append(risk_level)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT c.id::text AS chunk_id,
                   c.document_id::text AS document_id,
                   c.version_id::text AS version_id,
                   c.heading AS title,
                   c.content,
                   c.metadata,
                   COALESCE(MAX(r.status), '') AS relation_status,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT r.id::text), NULL) AS relation_ids,
                   CASE
                     WHEN %s <> '' AND immutable_unaccent(lower({effective_heading})) LIKE immutable_unaccent(lower(%s)) THEN 2.0
                     WHEN %s <> '' AND immutable_unaccent(lower(c.content)) LIKE immutable_unaccent(lower(%s)) THEN 1.0
                     ELSE 0.0
                   END AS score
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            LEFT JOIN ai_document_relations r ON r.source_chunk_id = c.id
            WHERE {' AND '.join(clauses)}
            GROUP BY c.id, d.updated_at
            ORDER BY score DESC, d.updated_at DESC
            LIMIT %s
            """,
            [query, f"%{query}%", query, f"%{query}%", *params, limit],
        ).fetchall()
        if query:
            audit_tx(
                conn,
                actor="system",
                action="issue_router_search",
                entity_type="kb_index",
                entity_id=str(uuid.uuid4()),
                metadata={"query": query, "result_count": len(rows), "filters": {"audience": audience or [], "vertical": vertical or [], "collection": collection, "task_type": task_type or [], "risk_level": risk_level}},
            )
        return [issue_router_row(row) for row in rows]


def issue_router_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_refs = metadata.get("source_refs") if isinstance(metadata.get("source_refs"), list) else []
    return {
        "chunk_id": str(row.get("chunk_id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "version_id": str(row.get("version_id") or ""),
        "title": str(row.get("title") or ""),
        "issue_text": str(metadata.get("issue_text") or row.get("title") or ""),
        "content": str(row.get("content") or ""),
        "audience": list(metadata.get("audience") or []),
        "vertical": list(metadata.get("vertical") or []),
        "case_type": list(metadata.get("case_type") or []),
        "task_type": list(metadata.get("task_type") or []),
        "collection": str(metadata.get("collection_name") or metadata.get("collection_slug") or ""),
        "target_sop_title": str(metadata.get("target_sop_title") or ""),
        "target_sop_id": metadata.get("target_sop_id"),
        "tool_ids": list(metadata.get("tool_ids") or []),
        "relation_ids": list(row.get("relation_ids") or []),
        "relation_status": str(row.get("relation_status") or ""),
        "risk_level": str(metadata.get("risk_level") or ""),
        "review_status": str(metadata.get("review_status") or ""),
        "source_ref": source_refs[0] if source_refs and isinstance(source_refs[0], dict) else {},
        "metadata": metadata,
        "score": float(row.get("score") or 0),
    }


def list_tool_links(status: str = "active", collection: str = "") -> list[dict[str, Any]]:
    clauses = [
        "t.status = %s",
        "(t.source_version_id IS NULL OR EXISTS (SELECT 1 FROM ai_document_versions v WHERE v.id = t.source_version_id AND v.status = 'published' AND v.publish_state = 'published_ready'))",
    ]
    params: list[Any] = [status]
    if collection:
        clauses.append("t.metadata->>'collection_slug' = %s")
        params.append(collection)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT t.id::text AS id,
                   t.name,
                   t.url,
                   t.tool_type,
                   COALESCE(t.description, '') AS description,
                   COALESCE(t.owner_team, '') AS owner_team,
                   t.status,
                   t.source_document_id::text AS source_document_id,
                   t.source_version_id::text AS source_version_id,
                   COALESCE(t.source_ref, '{{}}'::jsonb) AS source_ref,
                   t.metadata,
                   t.created_at,
                   t.updated_at
            FROM tool_links t
            WHERE {' AND '.join(clauses)}
            ORDER BY t.tool_type, t.name
            """,
            params,
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["used_by"] = tool_used_by_tx(conn, item["id"])
            output.append(item)
        return output


def tool_used_by_tx(conn: Connection[Any], tool_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ch.id::text AS chunk_id,
               ch.heading,
               ch.metadata,
               d.title AS document_title
        FROM tool_links t
        JOIN ai_chunks ch ON ch.id = t.source_unit_id
        JOIN ai_documents d ON d.id = ch.document_id
        WHERE t.id = %s
        LIMIT 20
        """,
        (tool_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_action_templates(status: str = "approved", collection: str = "") -> list[dict[str, Any]]:
    clauses = [
        "status = %s",
        "(source_unit_id IS NULL OR EXISTS (SELECT 1 FROM ai_chunks ch JOIN ai_document_versions v ON v.id = ch.version_id WHERE ch.id = source_unit_id AND v.status = 'published' AND v.publish_state = 'published_ready'))",
    ]
    params: list[Any] = [status]
    if collection:
        clauses.append("metadata->>'collection_slug' = %s")
        params.append(collection)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id::text AS id,
                   name,
                   action_type,
                   description,
                   fields,
                   COALESCE(copy_template, '') AS copy_template,
                   related_tool_ids::text[] AS related_tool_ids,
                   source_unit_id::text AS source_unit_id,
                   status,
                   metadata,
                   created_at,
                   updated_at
            FROM action_templates
            WHERE {' AND '.join(clauses)}
            ORDER BY action_type, name
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def record_kb_event(action: str, entity_type: str, entity_id: str | None, actor: str, metadata: dict[str, Any] | None = None) -> dict[str, str]:
    event_id = str(uuid.uuid4())
    event_metadata = dict(metadata or {})
    event_entity_id = entity_id if is_uuid_text(entity_id) else event_id
    if entity_id and event_entity_id == event_id:
        event_metadata["supplied_entity_id"] = entity_id
    with connection() as conn:
        audit_tx(
            conn,
            actor=actor or "system",
            action=action,
            entity_type=entity_type or "kb_index",
            entity_id=event_entity_id,
            metadata=event_metadata,
        )
    return {"id": event_id, "status": "recorded"}


def is_uuid_text(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


FEEDBACK_LABELS = {
    "outdated": "Outdated",
    "wrong": "Wrong",
    "missing_step": "Missing step",
    "need_macro": "Need macro",
    "hard_to_understand": "Hard to understand",
    "search_result_wrong": "Search result wrong",
}


def list_feedback_queue(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   actor,
                   entity_type,
                   entity_id::text AS entity_id,
                   metadata,
                   created_at
            FROM ai_audit_events
            WHERE action = 'feedback_submitted'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 100), 500)),),
        ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = row.get("metadata") or {}
        feedback_type = str(metadata.get("feedback_type") or "wrong")
        key = f"{row['entity_type']}:{row['entity_id']}:{feedback_type}"
        item = grouped.get(key)
        created_at = row["created_at"]
        if not item:
            item = {
                "key": key,
                "entity_type": str(row["entity_type"] or ""),
                "entity_id": str(row["entity_id"] or ""),
                "target_title": str(metadata.get("target_title") or metadata.get("title") or ""),
                "source_title": str(metadata.get("source_title") or metadata.get("document_title") or ""),
                "feedback_type": feedback_type,
                "feedback_label": FEEDBACK_LABELS.get(feedback_type, feedback_type.replace("_", " ").title()),
                "count": 0,
                "last_seen": created_at,
                "sample_query": "",
                "sample_comment": "",
                "suggested_action": suggested_feedback_action(feedback_type),
                "severity": feedback_severity(feedback_type),
                "metadata": {},
            }
            grouped[key] = item
        item["count"] += 1
        if created_at > item["last_seen"]:
            item["last_seen"] = created_at
        if not item["target_title"]:
            item["target_title"] = str(metadata.get("target_title") or metadata.get("title") or "")
        if not item["source_title"]:
            item["source_title"] = str(metadata.get("source_title") or metadata.get("document_title") or "")
        if not item["sample_query"]:
            item["sample_query"] = str(metadata.get("sample_query") or metadata.get("query") or "")
        if not item["sample_comment"]:
            item["sample_comment"] = str(metadata.get("comment") or metadata.get("reason") or "")
        item["metadata"] = {
            "last_event_id": row["id"],
            "last_actor": row["actor"],
            "last_metadata": metadata,
        }
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        grouped.values(),
        key=lambda item: (
            severity_rank.get(str(item["severity"]), 3),
            -int(item["count"]),
            -item["last_seen"].timestamp(),
        ),
    )


def ops_analytics(window_days: int = 7) -> dict[str, Any]:
    window = max(1, min(int(window_days or 7), 90))
    with connection() as conn:
        conn.row_factory = dict_row
        audit_rows = conn.execute(
            """
            SELECT actor,
                   action,
                   entity_type,
                   entity_id::text AS entity_id,
                   metadata,
                   created_at
            FROM ai_audit_events
            WHERE created_at >= now() - (%s::text || ' days')::interval
            ORDER BY created_at ASC
            """,
            (str(window),),
        ).fetchall()
        retrieval_rows = conn.execute(
            """
            SELECT query, filters, mode, result_count, latency_ms, created_at
            FROM ai_retrieval_events
            WHERE created_at >= now() - (%s::text || ' days')::interval
            ORDER BY created_at ASC
            """,
            (str(window),),
        ).fetchall()
    action_counts: dict[str, int] = {}
    actor_set = set()
    clicked_ranks: list[float] = []
    search_events: dict[str, datetime] = {}
    useful_deltas_ms: list[float] = []
    feedback_counts: dict[str, int] = {}
    query_counts: dict[str, int] = {}
    query_last_seen: dict[str, datetime] = {}
    useful_actions = {"quick_answer_open", "action_template_copy", "macro_copy"}
    click_actions = {"search_result_click", "quick_answer_open", "full_sop_open", "action_template_copy", "macro_copy"}
    for row in audit_rows:
        action = str(row["action"] or "")
        metadata = row.get("metadata") or {}
        action_counts[action] = action_counts.get(action, 0) + 1
        actor = str(row["actor"] or "").strip()
        if actor:
            actor_set.add(actor)
        if action == "sop_search":
            event_id = str(metadata.get("search_event_id") or "")
            if event_id:
                search_events[event_id] = row["created_at"]
            query = str(metadata.get("query") or "").strip()
            if query:
                query_counts[query] = query_counts.get(query, 0) + 1
                query_last_seen[query] = row["created_at"]
        if action in click_actions:
            rank = metadata.get("rank")
            if isinstance(rank, (int, float)) and rank > 0:
                clicked_ranks.append(float(rank))
            event_id = str(metadata.get("search_event_id") or "")
            started_at = search_events.get(event_id)
            if started_at:
                useful_deltas_ms.append(max(0, (row["created_at"] - started_at).total_seconds() * 1000))
        if action == "feedback_submitted":
            feedback_type = str(metadata.get("feedback_type") or "wrong")
            feedback_counts[feedback_type] = feedback_counts.get(feedback_type, 0) + 1
    retrieval_total = len(retrieval_rows)
    retrieval_success = sum(1 for row in retrieval_rows if int(row.get("result_count") or 0) > 0)
    zero_rate = round(((retrieval_total - retrieval_success) / retrieval_total) * 100) if retrieval_total else 0
    success_rate = round((retrieval_success / retrieval_total) * 100) if retrieval_total else 0
    avg_rank = sum(clicked_ranks) / len(clicked_ranks) if clicked_ranks else None
    useful_sorted = sorted(useful_deltas_ms)
    median_time_ms = median_from_sorted(useful_sorted)
    quick_action_count = sum(action_counts.get(action, 0) for action in useful_actions)
    wrong_outdated = feedback_counts.get("wrong", 0) + feedback_counts.get("outdated", 0) + feedback_counts.get("search_result_wrong", 0)
    popular_queries = [
        {"query": query, "count": count, "last_seen": query_last_seen[query]}
        for query, count in sorted(query_counts.items(), key=lambda item: (item[1], query_last_seen[item[0]], item[0]), reverse=True)[:6]
    ]
    recent_queries = [
        {"query": query, "count": query_counts[query], "last_seen": last_seen}
        for query, last_seen in sorted(query_last_seen.items(), key=lambda item: item[1], reverse=True)[:6]
    ]
    events = {
        **action_counts,
        "retrieval_total": retrieval_total,
        "retrieval_success": retrieval_success,
        "weekly_active_actors": len(actor_set),
    }
    return {
        "window_days": window,
        "generated_at": datetime.now(timezone.utc),
        "events": events,
        "popular_queries": popular_queries,
        "recent_queries": recent_queries,
        "metrics": [
            {
                "key": "median_time_to_useful_sop",
                "label": "Median time to useful SOP",
                "value": f"{median_time_ms / 1000:.1f}s" if median_time_ms is not None else "Not enough clicks",
                "target": "<15s",
                "detail": "Measured from SOP search to first quick answer, full SOP, macro, or action-template use when the UI can connect both events.",
                "tone": "warning" if median_time_ms is not None and median_time_ms > 15000 else "default",
            },
            {
                "key": "search_success_rate",
                "label": "Search success rate",
                "value": f"{success_rate}%",
                "target": ">=85%",
                "detail": f"{retrieval_success}/{retrieval_total} retrieval calls returned at least one approved result.",
                "tone": "warning" if retrieval_total and success_rate < 85 else "default",
            },
            {
                "key": "zero_result_rate",
                "label": "Zero-result rate",
                "value": f"{zero_rate}%",
                "target": "<5-8%",
                "detail": "Share of retrieval calls with no approved result.",
                "tone": "warning" if retrieval_total and zero_rate > 8 else "default",
            },
            {
                "key": "avg_clicked_rank",
                "label": "Avg clicked rank",
                "value": f"{avg_rank:.1f}" if avg_rank is not None else "No clicks yet",
                "target": "<=3",
                "detail": f"{len(clicked_ranks)} ranked click events recorded.",
                "tone": "warning" if avg_rank is not None and avg_rank > 3 else "default",
            },
            {
                "key": "weekly_active_cs",
                "label": "Tracked active CS",
                "value": str(len(actor_set)),
                "target": ">=85% with auth",
                "detail": "MVP has no real auth, so this is distinct event actors, not real headcount.",
                "tone": "default",
            },
            {
                "key": "quick_answer_action_usage",
                "label": "Quick answer/action usage",
                "value": str(quick_action_count),
                "target": "Up week over week",
                "detail": "Proxy north star: quick_answer_open + action_template_copy + macro_copy.",
                "tone": "default",
            },
            {
                "key": "wrong_outdated_reports",
                "label": "Wrong/outdated reports",
                "value": str(wrong_outdated),
                "target": "Down month over month",
                "detail": "Feedback that directly indicates policy trust or ranking problems.",
                "tone": "warning" if wrong_outdated else "default",
            },
        ],
    }


def suggested_feedback_action(feedback_type: str) -> str:
    return {
        "outdated": "Create a draft version from the source SOP and verify owner/date before republish.",
        "wrong": "Review the cited unit against the source file, then fix the unit or relation before agents rely on it.",
        "missing_step": "Add the missing operational step to a draft version or attach the correct source evidence.",
        "need_macro": "Create or link an approved macro/action template for this rule.",
        "hard_to_understand": "Rewrite the unit into clearer CS handling language without changing policy meaning.",
        "search_result_wrong": "Inspect query, clicked rank, collection metadata, synonyms, and retrieval title/content labels.",
    }.get(feedback_type, "Review the source evidence and decide whether to draft an SOP update.")


def feedback_severity(feedback_type: str) -> str:
    if feedback_type in {"wrong", "outdated", "missing_step", "search_result_wrong"}:
        return "high"
    if feedback_type == "need_macro":
        return "medium"
    return "low"


def median_from_sorted(values: list[float]) -> float | None:
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / 2


def list_document_relations(status: str = "unresolved") -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("r.status = %s")
        params.append(pg_text(status))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT r.id::text AS id,
                   r.source_document_id::text AS source_document_id,
                   r.source_version_id::text AS source_version_id,
                   r.source_chunk_id::text AS source_chunk_id,
                   source.title AS source_title,
                   r.target_title,
                   r.target_document_id::text AS target_document_id,
                   r.target_version_id::text AS target_version_id,
                   COALESCE(target.title, '') AS target_title_resolved,
                   r.relation_type,
                   r.status,
                   r.created_by,
                   r.reviewed_by,
                   r.reviewed_at,
                   r.rejection_reason,
                   r.metadata,
                   r.created_at,
                   r.updated_at
            FROM ai_document_relations r
            JOIN ai_documents source ON source.id = r.source_document_id
            LEFT JOIN ai_documents target ON target.id = r.target_document_id
            {where}
            ORDER BY
              CASE r.status WHEN 'unresolved' THEN 0 WHEN 'suggested' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END,
              r.updated_at DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def create_document_relation(
    *,
    source_document_id: str,
    source_version_id: str | None,
    source_chunk_id: str | None,
    target_title: str,
    target_document_id: str | None,
    relation_type: str,
    actor: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relation_type = normalize_relation_type(relation_type)
    clean_metadata = metadata if isinstance(metadata, dict) else {}
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            source = conn.execute(
                """
                SELECT d.id::text AS document_id,
                       COALESCE(%s, d.current_version_id::text) AS version_id
                FROM ai_documents d
                WHERE d.id = %s AND d.status = 'active'
                """,
                (source_version_id, source_document_id),
            ).fetchone()
            if not source or not source.get("version_id"):
                raise LookupError("source_document_not_found")
            if source_version_id:
                version_exists = conn.execute(
                    "SELECT 1 FROM ai_document_versions WHERE id = %s AND document_id = %s",
                    (source_version_id, source_document_id),
                ).fetchone()
                if not version_exists:
                    raise LookupError("source_version_not_found")
            if source_chunk_id:
                chunk_exists = conn.execute(
                    "SELECT 1 FROM ai_chunks WHERE id = %s AND document_id = %s AND version_id = %s",
                    (source_chunk_id, source_document_id, source["version_id"]),
                ).fetchone()
                if not chunk_exists:
                    raise LookupError("source_chunk_not_found")

            resolved_target = None
            if target_document_id:
                resolved_target = published_target_document_tx(conn, target_document_id)
                if not resolved_target:
                    raise LookupError("target_document_not_found")
                target_title = target_title or str(resolved_target.get("title") or "")
            target_title = clean_relation_title(target_title)
            if not target_title:
                raise ValueError("target_title_required")
            normalized_title = normalize_phrase(target_title)[:300]
            status = "approved" if resolved_target else "unresolved"
            relation_source = str(clean_metadata.get("relation_source") or "manual")
            if not resolved_target and relation_source != "manual":
                resolved_target = exact_relation_target_tx(conn, normalized_title, source_document_id)
                if resolved_target:
                    status = "suggested"
            metadata_payload = {
                **clean_metadata,
                "relation_source": relation_source,
                "match_status": "manual_target_approved" if status == "approved" else ("exact_title_candidate" if status == "suggested" else "manual_unresolved"),
            }
            existing = conn.execute(
                """
                SELECT id::text AS id
                FROM ai_document_relations
                WHERE source_document_id = %s
                  AND source_version_id = %s
                  AND source_chunk_id IS NOT DISTINCT FROM %s
                  AND target_title_normalized = %s
                  AND relation_type = %s
                """,
                (source_document_id, source["version_id"], source_chunk_id, normalized_title, relation_type),
            ).fetchone()
            relation_id = str(existing["id"]) if existing else str(uuid.uuid4())
            if existing:
                conn.execute(
                    """
                    UPDATE ai_document_relations
                    SET target_title = %s,
                        target_document_id = %s,
                        target_version_id = %s,
                        status = %s,
                        reviewed_by = CASE WHEN %s = 'approved' THEN %s ELSE reviewed_by END,
                        reviewed_at = CASE WHEN %s = 'approved' THEN now() ELSE reviewed_at END,
                        rejection_reason = '',
                        metadata = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        target_title,
                        resolved_target.get("document_id") if resolved_target else None,
                        resolved_target.get("version_id") if resolved_target else None,
                        status,
                        status,
                        pg_text(actor),
                        status,
                        pg_text(json.dumps(metadata_payload)),
                        relation_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ai_document_relations (
                      id, source_document_id, source_version_id, source_chunk_id,
                      target_title, target_title_normalized, target_document_id, target_version_id,
                      relation_type, status, created_by, reviewed_by, reviewed_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'approved' THEN %s ELSE NULL END, CASE WHEN %s = 'approved' THEN now() ELSE NULL END, %s::jsonb)
                    """,
                    (
                        relation_id,
                        source_document_id,
                        source["version_id"],
                        source_chunk_id,
                        target_title,
                        normalized_title,
                        resolved_target.get("document_id") if resolved_target else None,
                        resolved_target.get("version_id") if resolved_target else None,
                        relation_type,
                        status,
                        pg_text(actor or "cs-ops-ui"),
                        status,
                        pg_text(actor),
                        status,
                        pg_text(json.dumps(metadata_payload)),
                    ),
                )
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="document_relation_create",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata={"status": status, "relation_type": relation_type, "source_document_id": source_document_id},
            )
            if status == "unresolved":
                audit_tx(
                    conn,
                    actor=pg_text(actor),
                    action="unresolved_relation_created",
                    entity_type="ai_document_relation",
                    entity_id=relation_id,
                    metadata={"relation_type": relation_type, "source_document_id": source_document_id, "target_title": target_title},
                )
    return relation_by_id(relation_id)


def published_target_document_tx(conn: Connection[Any], target_document_id: str) -> dict[str, Any] | None:
    conn.row_factory = dict_row
    row = conn.execute(
        """
        SELECT d.id::text AS document_id,
               v.id::text AS version_id,
               d.title,
               v.status AS version_status
        FROM ai_documents d
        JOIN ai_document_versions v ON v.id = d.current_version_id
        WHERE d.id = %s AND d.status = 'active'
        """,
        (target_document_id,),
    ).fetchone()
    if not row:
        return None
    if row["version_status"] != "published":
        raise ValueError("target_document_must_have_published_current_version")
    return dict(row)


def assign_document_relation(relation_id: str, target_document_id: str, actor: str) -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            target = conn.execute(
                """
                SELECT d.id::text AS document_id,
                       d.current_version_id::text AS version_id,
                       v.status AS version_status
                FROM ai_documents d
                JOIN ai_document_versions v ON v.id = d.current_version_id
                WHERE d.id = %s AND d.status = 'active'
                """,
                (target_document_id,),
            ).fetchone()
            if not target:
                raise LookupError("target_document_not_found")
            if target["version_status"] != "published":
                raise ValueError("target_document_must_have_published_current_version")

            row = conn.execute(
                """
                UPDATE ai_document_relations
                SET target_document_id = %s,
                    target_version_id = %s,
                    status = 'approved',
                    reviewed_by = %s,
                    reviewed_at = now(),
                    rejection_reason = '',
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text AS relation_id,
                          source_document_id::text AS source_document_id,
                          target_document_id::text AS target_document_id,
                          target_version_id::text AS target_version_id,
                          relation_type,
                          status
                """,
                (target_document_id, target["version_id"], pg_text(actor), relation_id),
            ).fetchone()
            if not row:
                raise LookupError("relation_not_found")
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="document_relation_approve",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata=dict(row),
            )
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="relation_approved",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata=dict(row),
            )
    return relation_by_id(relation_id)


def reject_document_relation(relation_id: str, actor: str, rejection_reason: str = "") -> dict[str, Any]:
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = conn.execute(
                """
                UPDATE ai_document_relations
                SET status = 'rejected',
                    reviewed_by = %s,
                    reviewed_at = now(),
                    rejection_reason = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text AS relation_id,
                          source_document_id::text AS source_document_id,
                          relation_type,
                          status
                """,
                (pg_text(actor), pg_text(rejection_reason), relation_id),
            ).fetchone()
            if not row:
                raise LookupError("relation_not_found")
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="document_relation_reject",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata=dict(row),
            )
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="relation_rejected",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata=dict(row),
            )
    return relation_by_id(relation_id)


def archive_document_relation(relation_id: str, actor: str, archive_reason: str = "") -> dict[str, Any]:
    archived_metadata = {
        "archive_reason": archive_reason or "manual_archive",
        "archived_by": actor,
    }
    with connection() as conn:
        with conn.transaction():
            conn.row_factory = dict_row
            row = conn.execute(
                """
                UPDATE ai_document_relations
                SET status = 'archived',
                    reviewed_by = %s,
                    reviewed_at = now(),
                    metadata = metadata || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text AS relation_id,
                          source_document_id::text AS source_document_id,
                          target_document_id::text AS target_document_id,
                          relation_type,
                          status
                """,
                (pg_text(actor), pg_text(json.dumps(archived_metadata)), relation_id),
            ).fetchone()
            if not row:
                raise LookupError("relation_not_found")
            audit_tx(
                conn,
                actor=pg_text(actor),
                action="document_relation_archive",
                entity_type="ai_document_relation",
                entity_id=relation_id,
                metadata=dict(row) | {"archive_reason": archived_metadata["archive_reason"]},
            )
    return relation_by_id(relation_id)


def relation_by_id(relation_id: str) -> dict[str, Any]:
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            SELECT r.id::text AS id,
                   r.source_document_id::text AS source_document_id,
                   r.source_version_id::text AS source_version_id,
                   r.source_chunk_id::text AS source_chunk_id,
                   source.title AS source_title,
                   r.target_title,
                   r.target_document_id::text AS target_document_id,
                   r.target_version_id::text AS target_version_id,
                   COALESCE(target.title, '') AS target_title_resolved,
                   r.relation_type,
                   r.status,
                   r.created_by,
                   r.reviewed_by,
                   r.reviewed_at,
                   r.rejection_reason,
                   r.metadata,
                   r.created_at,
                   r.updated_at
            FROM ai_document_relations r
            JOIN ai_documents source ON source.id = r.source_document_id
            LEFT JOIN ai_documents target ON target.id = r.target_document_id
            WHERE r.id = %s
            """,
            (relation_id,),
        ).fetchone()
        if not row:
            raise LookupError("relation_not_found")
        return dict(row)


def rerank_structural_matches(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_query = normalize_phrase(query)
    query_tokens = [token for token in normalized_query.split() if len(token) >= 4]
    if not query_tokens and not normalized_query:
        return rows
    for row in rows:
        metadata = row.get("metadata") or {}
        sheet = normalize_phrase(str(metadata.get("sheet_name") or ""))
        heading = normalize_phrase(meaningful_search_label(row.get("heading") or "", row.get("content") or "", str(metadata.get("unit_type") or row.get("section") or "")))
        if is_bad_search_label(row.get("heading") or "", row.get("content") or ""):
            heading = ""
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
                   publish_state,
                   checksum,
                   chunk_count,
                   document_type,
                   review_status,
                   extraction_confidence::float AS extraction_confidence,
                   change_summary,
                   published_at,
                   indexed_at,
                   COALESCE(indexing_error, '') AS indexing_error,
                   published_ready_at,
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
            if review_status == "rejected":
                merged_metadata["manual_curation_status"] = "rejected"
                merged_metadata["source_evidence_only"] = True
                merged_metadata["index_eligible"] = False
                merged_metadata["publish_blocked"] = False
                merged_metadata["publish_blocked_reason"] = ""
                merged_metadata["rejected_at"] = datetime.now(timezone.utc).isoformat()
                merged_metadata["rejected_by"] = actor
            if review_status in {"reviewed", "approved"}:
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


def delete_extraction_unit(*, unit_id: str, actor: str) -> dict[str, Any]:
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
                       c.metadata,
                       v.status AS version_status
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

            conn.execute("DELETE FROM ai_chunks WHERE id = %s", (unit_id,))
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
                (row["version_id"], row["version_id"]),
            )
            conn.execute(
                "UPDATE ai_documents SET updated_at = now() WHERE id = %s",
                (row["document_id"],),
            )
            audit_tx(
                conn,
                actor=actor,
                action="extraction_unit_delete",
                entity_type="ai_chunk",
                entity_id=unit_id,
                metadata={
                    "document_id": row["document_id"],
                    "version_id": row["version_id"],
                    "unit_index": row["unit_index"],
                    "unit_type": row["section"],
                    "title": row["title"],
                },
            )

    return {
        "deleted": True,
        "document_id": row["document_id"],
        "unit_id": unit_id,
        "version_id": row["version_id"],
    }


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
    effective_heading = EFFECTIVE_HEADING_SQL
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
                           concat_ws(' ', {effective_heading}, c.section, c.metadata->>'sheet_name', c.content)
                         )
                       ),
                       to_tsquery('simple', %s)
                     )
                     + CASE WHEN immutable_unaccent(lower(COALESCE(c.metadata->>'sheet_name', ''))) LIKE %s THEN 1.2 ELSE 0 END
                     + CASE WHEN immutable_unaccent(lower(COALESCE({effective_heading}, ''))) LIKE %s THEN 0.8 ELSE 0 END
                   ) AS score
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE {where_sql}
              AND to_tsvector(
                    'simple',
                    immutable_unaccent(concat_ws(' ', {effective_heading}, c.section, c.metadata->>'sheet_name', c.content))
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


def approved_relation_target_rows(source_document_ids: list[str], exclude_chunk_ids: list[str], limit: int) -> list[dict[str, Any]]:
    source_ids = list(dict.fromkeys([item for item in source_document_ids if item]))
    if not source_ids or limit <= 0:
        return []
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT DISTINCT ON (c.id)
                   c.id AS chunk_id,
                   c.document_id,
                   c.version_id,
                   target.title,
                   COALESCE(c.metadata->>'source_filename', target.source_filename) AS source_filename,
                   v.version_number,
                   c.chunk_index,
                   c.section,
                   c.heading,
                   c.content,
                   jsonb_set(
                     jsonb_set(
                       c.metadata,
                       '{relation_source_document_id}',
                       to_jsonb(r.source_document_id::text),
                       true
                     ),
                     '{relation_type}',
                     to_jsonb(r.relation_type::text),
                     true
                   ) AS metadata,
                   0.005::float AS score,
                   0.0::float AS lexical_score,
                   0.0::float AS vector_score,
                   ARRAY['approved_relation']::text[] AS rank_source,
                   999 AS best_rank
            FROM ai_document_relations r
            JOIN ai_documents target ON target.id = r.target_document_id
            JOIN ai_document_versions v ON v.id = r.target_version_id
            JOIN ai_chunks c ON c.document_id = target.id AND c.version_id = v.id
            WHERE r.status = 'approved'
              AND r.source_document_id = ANY(%s)
              AND r.relation_type <> 'possible_conflict'
              AND target.status = 'active'
              AND target.current_version_id = v.id
              AND v.status = 'published'
              AND v.publish_state = 'published_ready'
              AND COALESCE(c.metadata->>'review_status', '') = 'approved'
              AND COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)
              AND COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'
              AND NOT (c.id::text = ANY(%s))
            ORDER BY c.id, CASE WHEN COALESCE(c.metadata->>'retrieval_scope', '') = 'document' THEN 0 ELSE 1 END, c.chunk_index
            LIMIT %s
            """,
            (source_ids, ["structured", "manually_curated"], exclude_chunk_ids or [""], limit),
        ).fetchall()
        return [dict(row) for row in rows]


def approved_relation_target_rows_for_chunks(source_chunk_ids: list[str], exclude_chunk_ids: list[str], limit: int) -> list[dict[str, Any]]:
    source_ids = list(dict.fromkeys([item for item in source_chunk_ids if item]))
    if not source_ids or limit <= 0:
        return []
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT DISTINCT ON (c.id)
                   c.id AS chunk_id,
                   c.document_id,
                   c.version_id,
                   target.title,
                   COALESCE(c.metadata->>'source_filename', target.source_filename) AS source_filename,
                   v.version_number,
                   c.chunk_index,
                   c.section,
                   c.heading,
                   c.content,
                   jsonb_set(
                     jsonb_set(
                       jsonb_set(
                         c.metadata,
                         '{relation_source_chunk_id}',
                         to_jsonb(r.source_chunk_id::text),
                         true
                       ),
                       '{relation_source_document_id}',
                       to_jsonb(r.source_document_id::text),
                       true
                     ),
                     '{relation_type}',
                     to_jsonb(r.relation_type::text),
                     true
                   ) AS metadata,
                   0.005::float AS score,
                   0.0::float AS lexical_score,
                   0.0::float AS vector_score,
                   ARRAY['approved_relation']::text[] AS rank_source,
                   999 AS best_rank
            FROM ai_document_relations r
            JOIN ai_documents target ON target.id = r.target_document_id
            JOIN ai_document_versions v ON v.id = r.target_version_id
            JOIN ai_chunks c ON c.document_id = target.id AND c.version_id = v.id
            WHERE r.status = 'approved'
              AND r.source_chunk_id::text = ANY(%s)
              AND r.relation_type <> 'possible_conflict'
              AND target.status = 'active'
              AND target.current_version_id = v.id
              AND v.status = 'published'
              AND v.publish_state = 'published_ready'
              AND COALESCE(c.metadata->>'review_status', '') = 'approved'
              AND COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)
              AND COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'
              AND NOT (c.id::text = ANY(%s))
            ORDER BY c.id, CASE WHEN COALESCE(c.metadata->>'retrieval_scope', '') = 'document' THEN 0 ELSE 1 END, c.chunk_index
            LIMIT %s
            """,
            (source_ids, ["structured", "manually_curated"], exclude_chunk_ids or [""], limit),
        ).fetchall()
        return [dict(row) for row in rows]


def published_chunk_rows_by_ids(chunk_ids: list[str], exclude_chunk_ids: list[str] | None = None, limit: int = 6) -> list[dict[str, Any]]:
    ids = list(dict.fromkeys([item for item in chunk_ids if item]))
    if not ids or limit <= 0:
        return []
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
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
                   0.32::float AS score,
                   0.0::float AS lexical_score,
                   0.0::float AS vector_score,
                   ARRAY['session_context_source']::text[] AS rank_source,
                   0 AS best_rank
            FROM ai_chunks c
            JOIN ai_documents d ON d.id = c.document_id
            JOIN ai_document_versions v ON v.id = c.version_id
            WHERE c.id::text = ANY(%s)
              AND d.status = 'active'
              AND d.current_version_id = v.id
              AND v.status = 'published'
              AND v.publish_state = 'published_ready'
              AND COALESCE(c.metadata->>'review_status', '') = 'approved'
              AND COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)
              AND COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'
              AND NOT (c.id::text = ANY(%s))
            ORDER BY array_position(%s::text[], c.id::text)
            LIMIT %s
            """,
            (ids, ["structured", "manually_curated"], exclude_chunk_ids or [""], ids, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def parent_sop_context_rows(chunk_ids: list[str], exclude_chunk_ids: list[str], limit: int) -> list[dict[str, Any]]:
    source_ids = list(dict.fromkeys([item for item in chunk_ids if item]))
    if not source_ids or limit <= 0:
        return []
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            WITH source_scope AS (
              SELECT DISTINCT document_id, version_id
              FROM ai_chunks
              WHERE id::text = ANY(%s)
            )
            SELECT DISTINCT ON (c.id)
                   c.id AS chunk_id,
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
                   0.003::float AS score,
                   0.0::float AS lexical_score,
                   0.0::float AS vector_score,
                   ARRAY['parent_sop_context']::text[] AS rank_source,
                   1000 AS best_rank
            FROM source_scope s
            JOIN ai_documents d ON d.id = s.document_id
            JOIN ai_document_versions v ON v.id = s.version_id
            JOIN ai_chunks c ON c.document_id = s.document_id AND c.version_id = s.version_id
            WHERE d.status = 'active'
              AND d.current_version_id = v.id
              AND v.status = 'published'
              AND v.publish_state = 'published_ready'
              AND COALESCE(c.metadata->>'review_status', '') = 'approved'
              AND COALESCE(c.metadata->>'extraction_status', '') = ANY(%s)
              AND COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'
              AND COALESCE(c.metadata->>'unit_type', c.section) = 'full_sop'
              AND NOT (c.id::text = ANY(%s))
            ORDER BY c.id, CASE WHEN COALESCE(c.metadata->>'retrieval_scope', '') = 'document' THEN 0 ELSE 1 END, c.chunk_index
            LIMIT %s
            """,
            (source_ids, ["structured", "manually_curated"], exclude_chunk_ids or [""], limit),
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
        clauses.append("v.publish_state = 'published_ready'")
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
    if filters.collections:
        clauses.append("c.metadata->>'collection_slug' = ANY(%s)")
        params.append(filters.collections)
    if filters.task_types:
        clauses.append("(c.metadata->'task_type') ?| %s")
        params.append(filters.task_types)
    if filters.unit_types:
        clauses.append("COALESCE(c.metadata->>'unit_type', c.section) = ANY(%s)")
        params.append(filters.unit_types)

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


def list_chat_sessions(status: str = "active", limit: int = 50) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != "all":
        clauses.append("status = %s")
        params.append(pg_text(status))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(int(limit or 50), 100)))
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id::text AS id,
                   title,
                   summary,
                   model_route,
                   filters,
                   status,
                   message_count,
                   last_message_at,
                   created_at,
                   updated_at
            FROM ai_chat_sessions
            {where}
            ORDER BY COALESCE(last_message_at, created_at) DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def create_chat_session(title: str = "", model_route: str = "simple", filters: dict[str, Any] | None = None) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    clean_title = pg_text(title).strip() or "New chat"
    with connection() as conn:
        conn.row_factory = dict_row
        conn.execute(
            """
            INSERT INTO ai_chat_sessions (id, title, model_route, filters)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (session_id, clean_title[:120], pg_text(model_route or "simple"), jsonb_text(filters or {})),
        )
    return chat_session_by_id(session_id)


def update_chat_session(
    session_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    model_route: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = chat_session_by_id(session_id)
    next_title = current["title"] if title is None else (pg_text(title).strip() or current["title"])[:120]
    next_status = current["status"] if status is None else status
    next_model_route = current["model_route"] if model_route is None else pg_text(model_route or current["model_route"])
    next_filters = current.get("filters") if filters is None else filters
    with connection() as conn:
        conn.execute(
            """
            UPDATE ai_chat_sessions
            SET title = %s,
                status = %s,
                model_route = %s,
                filters = %s::jsonb,
                updated_at = now()
            WHERE id = %s
            """,
            (next_title, next_status, next_model_route, jsonb_text(next_filters or {}), session_id),
        )
    return chat_session_by_id(session_id)


def chat_session_by_id(session_id: str) -> dict[str, Any]:
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            SELECT id::text AS id,
                   title,
                   summary,
                   model_route,
                   filters,
                   status,
                   message_count,
                   last_message_at,
                   created_at,
                   updated_at
            FROM ai_chat_sessions
            WHERE id = %s
            """,
            (session_id,),
        ).fetchone()
        if not row:
            raise LookupError("chat_session_not_found")
        return dict(row)


def list_chat_messages(session_id: str, limit: int = 80) -> list[dict[str, Any]]:
    chat_session_by_id(session_id)
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id::text AS id,
                   session_id::text AS session_id,
                   role,
                   content,
                   response_payload,
                   source_chunk_ids,
                   token_context_metadata,
                   created_at
            FROM ai_chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (session_id, max(1, min(int(limit or 80), 200))),
        ).fetchall()
        return [dict(row) for row in rows]


def recent_chat_user_messages(session_id: str, limit: int = 2) -> list[str]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT content
            FROM ai_chat_messages
            WHERE session_id = %s AND role = 'user'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, max(1, min(int(limit or 2), 4))),
        ).fetchall()
        return [str(row["content"]) for row in reversed(rows)]


def recent_chat_assistant_messages(session_id: str, limit: int = 1) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT content,
                   response_payload,
                   source_chunk_ids
            FROM ai_chat_messages
            WHERE session_id = %s AND role = 'assistant'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, max(1, min(int(limit or 1), 2))),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


def insert_chat_message(
    session_id: str,
    role: str,
    content: str,
    *,
    response_payload: dict[str, Any] | None = None,
    source_chunk_ids: list[str] | None = None,
    token_context_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    with connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            INSERT INTO ai_chat_messages (
              id, session_id, role, content, response_payload, source_chunk_ids, token_context_metadata
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            RETURNING id::text AS id,
                      session_id::text AS session_id,
                      role,
                      content,
                      response_payload,
                      source_chunk_ids,
                      token_context_metadata,
                      created_at
            """,
            (
                message_id,
                session_id,
                pg_text(role),
                pg_text(content),
                jsonb_text(response_payload or {}),
                jsonb_text(source_chunk_ids or []),
                jsonb_text(token_context_metadata or {}),
            ),
        ).fetchone()
        conn.execute(
            """
            UPDATE ai_chat_sessions
            SET message_count = message_count + 1,
                last_message_at = now(),
                updated_at = now()
            WHERE id = %s
            """,
            (session_id,),
        )
        return dict(row)


def update_chat_session_after_assistant(
    session_id: str,
    *,
    title: str | None,
    summary: str,
    model_route: str,
    filters: dict[str, Any],
) -> dict[str, Any]:
    with connection() as conn:
        conn.execute(
            """
            UPDATE ai_chat_sessions
            SET title = COALESCE(NULLIF(%s, ''), title),
                summary = %s,
                model_route = %s,
                filters = %s::jsonb,
                updated_at = now()
            WHERE id = %s
            """,
            (
                pg_text((title or "")[:120]),
                pg_text(summary[:700]),
                pg_text(model_route or "simple"),
                jsonb_text(filters or {}),
                session_id,
            ),
        )
    return chat_session_by_id(session_id)


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
