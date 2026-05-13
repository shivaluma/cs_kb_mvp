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
    CHECK (relation_type IN ('references', 'requires', 'must_follow', 'routes_to', 'escalates_to', 'uses_macro', 'uses_tool', 'has_action_template', 'has_case_reason', 'exception_of', 'supersedes', 'child_of', 'parent_of', 'modifies', 'related_to', 'possible_conflict')),
  CONSTRAINT ai_document_relations_status_check
    CHECK (status IN ('suggested', 'unresolved', 'approved', 'rejected', 'archived')),
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
);

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
);

CREATE TABLE IF NOT EXISTS tool_links (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL,
  url text NOT NULL UNIQUE,
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
  updated_at timestamptz NOT NULL DEFAULT now()
);

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
);

CREATE INDEX IF NOT EXISTS idx_ai_documents_status ON ai_documents(status);
CREATE INDEX IF NOT EXISTS idx_ai_document_versions_status ON ai_document_versions(status);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_document_version ON ai_chunks(document_id, version_id);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_status ON ai_document_relations(status);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_source ON ai_document_relations(source_document_id, source_version_id);
CREATE INDEX IF NOT EXISTS idx_ai_document_relations_target ON ai_document_relations(target_document_id, target_version_id);
CREATE INDEX IF NOT EXISTS idx_kb_collection_items_collection ON kb_collection_items(collection_id, status);
CREATE INDEX IF NOT EXISTS idx_kb_collection_items_item ON kb_collection_items(item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_tool_links_status ON tool_links(status);
CREATE INDEX IF NOT EXISTS idx_action_templates_status ON action_templates(status);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_hnsw ON ai_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_content_unaccent_fts ON ai_chunks USING gin (to_tsvector('simple', immutable_unaccent(content)));
CREATE INDEX IF NOT EXISTS idx_ai_chunks_metadata ON ai_chunks USING gin (metadata);
