create table if not exists public.lab_status (
  id text primary key default 'robot',
  stage text not null default 'IDLE',
  detail text not null default '',
  completed integer not null default 0,
  candidates integer not null default 0,
  validated integer not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.lab_strategies (
  strategy_id text primary key,
  agent text not null,
  parent_id text,
  stage text not null,
  fingerprint text not null,
  params jsonb not null default '{}'::jsonb,
  backtest jsonb not null default '{}'::jsonb,
  forward_test jsonb,
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.lab_status enable row level security;
alter table public.lab_strategies enable row level security;

drop policy if exists "lab status lecture" on public.lab_status;
create policy "lab status lecture" on public.lab_status
  for select to authenticated using (true);

drop policy if exists "lab strategies lecture" on public.lab_strategies;
create policy "lab strategies lecture" on public.lab_strategies
  for select to authenticated using (true);

comment on table public.lab_strategies is
  'Journal des strategies testees par le Strategy Lab. Aucun ordre live.';
