CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS roles (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  email text NOT NULL UNIQUE,
  display_name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id uuid NOT NULL REFERENCES users(id),
  role_id uuid NOT NULL REFERENCES roles(id),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS categories (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  key text NOT NULL UNIQUE,
  label text NOT NULL,
  knowledge_type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tags (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical text NOT NULL UNIQUE,
  aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_reasons (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  code text NOT NULL UNIQUE,
  label text NOT NULL,
  vertical text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sops (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  summary text NOT NULL,
  audience jsonb NOT NULL DEFAULT '[]'::jsonb,
  vertical text NOT NULL,
  category_id uuid REFERENCES categories(id),
  status text NOT NULL DEFAULT 'active',
  current_version_id uuid,
  owner_team text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sop_versions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  sop_id uuid NOT NULL REFERENCES sops(id),
  version_number integer NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  change_summary text NOT NULL DEFAULT '',
  effective_from timestamptz,
  created_by uuid REFERENCES users(id),
  approved_by uuid REFERENCES users(id),
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (sop_id, version_number)
);

ALTER TABLE sops
  ADD CONSTRAINT sops_current_version_fk
  FOREIGN KEY (current_version_id) REFERENCES sop_versions(id);

CREATE TABLE IF NOT EXISTS sop_sections (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  version_id uuid NOT NULL REFERENCES sop_versions(id),
  section_type text NOT NULL,
  content jsonb NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, section_type)
);

CREATE TABLE IF NOT EXISTS sop_tags (
  sop_id uuid NOT NULL REFERENCES sops(id),
  tag_id uuid NOT NULL REFERENCES tags(id),
  PRIMARY KEY (sop_id, tag_id)
);

CREATE TABLE IF NOT EXISTS sop_case_reasons (
  sop_id uuid NOT NULL REFERENCES sops(id),
  case_reason_id uuid NOT NULL REFERENCES case_reasons(id),
  PRIMARY KEY (sop_id, case_reason_id)
);

CREATE TABLE IF NOT EXISTS sop_related_links (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  sop_id uuid NOT NULL REFERENCES sops(id),
  related_sop_id uuid REFERENCES sops(id),
  label text NOT NULL,
  url text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor_user_id uuid REFERENCES users(id),
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid REFERENCES users(id),
  user_role text NOT NULL DEFAULT '',
  query text NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_count integer NOT NULL DEFAULT 0,
  clicked_sop_id uuid REFERENCES sops(id),
  clicked_position integer,
  latency_ms integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sop_view_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid REFERENCES users(id),
  sop_id uuid NOT NULL REFERENCES sops(id),
  version_id uuid NOT NULL REFERENCES sop_versions(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid REFERENCES users(id),
  event_type text NOT NULL,
  query text NOT NULL DEFAULT '',
  response jsonb NOT NULL DEFAULT '{}'::jsonb,
  citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  feedback text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sop_chunks (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  sop_id uuid NOT NULL REFERENCES sops(id),
  version_id uuid NOT NULL REFERENCES sop_versions(id),
  section_type text NOT NULL,
  chunk_text text NOT NULL,
  embedding vector(1536),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sops_status ON sops(status);
CREATE INDEX IF NOT EXISTS idx_sop_versions_status ON sop_versions(status);
CREATE INDEX IF NOT EXISTS idx_search_events_created_at ON search_events(created_at);
CREATE INDEX IF NOT EXISTS idx_sop_view_events_created_at ON sop_view_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_events_created_at ON ai_events(created_at);
