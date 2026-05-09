CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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
);

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
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT search_synonym_groups_type_check
    CHECK (synonym_type IN ('regular', 'one_way', 'typo_correction', 'placeholder')),
  CONSTRAINT search_synonym_groups_status_check
    CHECK (status IN ('draft', 'in_review', 'active', 'archived', 'rejected'))
);

CREATE TABLE IF NOT EXISTS search_synonym_terms (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  group_id uuid NOT NULL REFERENCES search_synonym_groups(id) ON DELETE CASCADE,
  term text NOT NULL,
  normalized_term text NOT NULL,
  language text NOT NULL DEFAULT 'vi',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (group_id, normalized_term)
);

CREATE TABLE IF NOT EXISTS search_synonym_suggestions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical_key text NOT NULL DEFAULT '',
  suggested_terms jsonb NOT NULL DEFAULT '[]'::jsonb,
  source text NOT NULL DEFAULT 'analytics',
  confidence numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'pending',
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT search_synonym_suggestions_status_check
    CHECK (status IN ('pending', 'accepted', 'rejected', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_taxonomy_intents_status ON taxonomy_intents(status);
CREATE INDEX IF NOT EXISTS idx_search_synonym_groups_status ON search_synonym_groups(status);
CREATE INDEX IF NOT EXISTS idx_search_synonym_groups_canonical ON search_synonym_groups(canonical_key);
CREATE INDEX IF NOT EXISTS idx_search_synonym_terms_normalized ON search_synonym_terms(normalized_term);
CREATE INDEX IF NOT EXISTS idx_search_synonym_suggestions_status ON search_synonym_suggestions(status);

INSERT INTO taxonomy_intents (intent_key, domain, audience, related_tags, risk_level, status)
VALUES
  ('missing_item', 'food', 'customer', '["refund", "merchant", "order_issue"]'::jsonb, 'medium', 'active'),
  ('wrong_item', 'food', 'customer', '["refund", "merchant", "order_issue"]'::jsonb, 'medium', 'active'),
  ('refund', 'payment', 'customer', '["compensation", "payment"]'::jsonb, 'high', 'active'),
  ('cancel_trip', 'ride-hailing', 'customer', '["cancellation", "trip"]'::jsonb, 'medium', 'active')
ON CONFLICT (intent_key) DO NOTHING;

WITH group_seed(canonical_key, synonym_type, domain, audience, status, approved_by) AS (
  VALUES
    ('missing_item', 'one_way', 'food', 'customer', 'active', 'seed'),
    ('wrong_item', 'one_way', 'food', 'customer', 'active', 'seed'),
    ('refund', 'regular', 'payment', 'customer', 'active', 'seed'),
    ('cancel_trip', 'one_way', 'ride-hailing', 'customer', 'active', 'seed')
),
inserted_groups AS (
  INSERT INTO search_synonym_groups (
    canonical_key, synonym_type, domain, audience, status, created_by, approved_by
  )
  SELECT canonical_key, synonym_type, domain, audience, status, 'seed', approved_by
  FROM group_seed
  WHERE NOT EXISTS (
    SELECT 1
    FROM search_synonym_groups g
    WHERE g.canonical_key = group_seed.canonical_key
      AND g.synonym_type = group_seed.synonym_type
      AND g.status <> 'archived'
  )
  RETURNING id, canonical_key
),
all_groups AS (
  SELECT id, canonical_key FROM inserted_groups
  UNION
  SELECT id, canonical_key
  FROM search_synonym_groups
  WHERE (canonical_key, synonym_type) IN (
    ('missing_item', 'one_way'),
    ('wrong_item', 'one_way'),
    ('refund', 'regular'),
    ('cancel_trip', 'one_way')
  )
    AND status <> 'archived'
),
term_seed(canonical_key, term, normalized_term, language) AS (
  VALUES
    ('missing_item', 'thiếu món', 'thieu mon', 'vi'),
    ('missing_item', 'không nhận đủ món', 'khong nhan du mon', 'vi'),
    ('missing_item', 'khach khong nhan du mon', 'khach khong nhan du mon', 'vi'),
    ('missing_item', 'thiếu topping', 'thieu topping', 'vi'),
    ('missing_item', 'giao thiếu nước', 'giao thieu nuoc', 'vi'),
    ('missing_item', 'missing item', 'missing item', 'en'),
    ('wrong_item', 'sai món', 'sai mon', 'vi'),
    ('wrong_item', 'giao sai combo', 'giao sai combo', 'vi'),
    ('wrong_item', 'wrong item', 'wrong item', 'en'),
    ('refund', 'hoàn tiền', 'hoan tien', 'vi'),
    ('refund', 'bồi hoàn', 'boi hoan', 'vi'),
    ('refund', 'cashback', 'cashback', 'en'),
    ('refund', 'refund', 'refund', 'en'),
    ('cancel_trip', 'hủy cuốc', 'huy cuoc', 'vi'),
    ('cancel_trip', 'huy cuoc', 'huy cuoc', 'vi'),
    ('cancel_trip', 'cancel ride', 'cancel ride', 'en')
)
INSERT INTO search_synonym_terms (group_id, term, normalized_term, language)
SELECT g.id, t.term, t.normalized_term, t.language
FROM term_seed t
JOIN all_groups g ON g.canonical_key = t.canonical_key
ON CONFLICT (group_id, normalized_term) DO NOTHING;
