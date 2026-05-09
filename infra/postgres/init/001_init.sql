create extension if not exists "uuid-ossp";

create table if not exists sops (
  id uuid primary key default uuid_generate_v4(),
  code varchar(100) not null unique,
  title text not null,
  summary text not null,
  status varchar(20) not null default 'active',
  current_version_id uuid,
  owner_team varchar(120) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists sop_versions (
  id uuid primary key default uuid_generate_v4(),
  sop_id uuid not null references sops(id),
  version_number int not null,
  status varchar(20) not null,
  change_summary text not null default '',
  effective_from timestamptz,
  created_by uuid,
  approved_by uuid,
  published_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists search_events (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid,
  query text not null,
  filters jsonb not null default '{}'::jsonb,
  result_count int not null default 0,
  clicked_sop_id uuid,
  clicked_position int,
  latency_ms int not null default 0,
  created_at timestamptz not null default now()
);
