-- Etat live de l'agent maître : pilotage et audit visibles dans l'application.
create table if not exists public.alluxe_agent_status (
  id text primary key,
  state text not null default 'IDLE',
  task text not null default '',
  tool text not null default '',
  detail text not null default '',
  last_error text not null default '',
  updated_at timestamptz not null default now()
);

alter table public.alluxe_agent_status enable row level security;
drop policy if exists "agent status lecture admin" on public.alluxe_agent_status;
create policy "agent status lecture admin"
  on public.alluxe_agent_status for select to authenticated
  using (exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and p.is_admin
  ));

create table if not exists public.alluxe_agent_events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  event_type text not null,
  tool text not null default '',
  status text not null default 'ok',
  summary text not null default '',
  duration_ms integer not null default 0
);

alter table public.alluxe_agent_events enable row level security;
drop policy if exists "agent events lecture admin" on public.alluxe_agent_events;
create policy "agent events lecture admin"
  on public.alluxe_agent_events for select to authenticated
  using (exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and p.is_admin
  ));

create index if not exists alluxe_agent_events_recent_idx
  on public.alluxe_agent_events (created_at desc);

do $$
begin
  alter publication supabase_realtime add table public.alluxe_agent_status;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.alluxe_agent_events;
exception when duplicate_object then null;
end $$;

comment on table public.alluxe_agent_status is
  'Etat live de l agent Alluxe : tache, outil courant, erreur et derniere mise a jour.';
comment on table public.alluxe_agent_events is
  'Journal lisible des actions de l agent Alluxe, sans secrets ni contenu sensible.';
