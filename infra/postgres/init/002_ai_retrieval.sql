CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$
  SELECT unaccent('public.unaccent', $1)
$$;

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
);

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
);

ALTER TABLE ai_documents
  ADD CONSTRAINT ai_documents_current_version_fk
  FOREIGN KEY (current_version_id) REFERENCES ai_document_versions(id);

CREATE TABLE IF NOT EXISTS ai_chunks (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES ai_documents(id),
  version_id uuid NOT NULL REFERENCES ai_document_versions(id),
  chunk_index integer NOT NULL,
  section text NOT NULL DEFAULT 'body',
  heading text NOT NULL DEFAULT '',
  content text NOT NULL,
  token_count integer NOT NULL DEFAULT 0,
  embedding vector(384) NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, chunk_index)
);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ai_document_relations_type_check
    CHECK (relation_type IN ('requires', 'references')),
  CONSTRAINT ai_document_relations_status_check
    CHECK (status IN ('unresolved', 'approved', 'rejected')),
  UNIQUE (source_version_id, source_chunk_id, target_title_normalized, relation_type)
);

CREATE TABLE IF NOT EXISTS ai_retrieval_events (
  id uuid PRIMARY KEY,
  query text NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  mode text NOT NULL,
  result_count integer NOT NULL,
  latency_ms integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_audit_events (
  id uuid PRIMARY KEY,
  actor text NOT NULL DEFAULT 'system',
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_documents_status ON ai_documents(status);
CREATE INDEX IF NOT EXISTS idx_ai_document_versions_status ON ai_document_versions(status);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_document_version ON ai_chunks(document_id, version_id);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_status ON ai_document_relations(status);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_source ON ai_document_relations(source_document_id, source_version_id);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_target ON ai_document_relations(target_document_id, target_version_id);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_content_unaccent_fts ON ai_chunks USING gin (to_tsvector('simple', immutable_unaccent(content)));
CREATE INDEX IF NOT EXISTS idx_ai_chunks_metadata ON ai_chunks USING gin (metadata);
