-- Luna : mesures de performance par publication.
create table if not exists public.luna_performance (
  id uuid primary key default gen_random_uuid(),
  publication_id uuid not null references public.luna_publications(id) on delete cascade,
  platform text not null,
  measured_at timestamptz not null default now(),
  views bigint not null default 0,
  likes bigint not null default 0,
  comments bigint not null default 0,
  shares bigint not null default 0,
  saves bigint not null default 0,
  watch_time_seconds numeric not null default 0,
  completion_rate numeric,
  followers_delta integer not null default 0,
  revenue_eur numeric(12,4) not null default 0,
  qualified_views bigint not null default 0,
  sponsored boolean not null default false,
  raw jsonb not null default '{}',
  unique(publication_id, platform, measured_at)
);

alter table public.luna_performance enable row level security;
alter table public.luna_performance force row level security;

create policy "luna performance : lecture admin uniquement"
  on public.luna_performance for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

revoke all on public.luna_performance from anon, authenticated;
grant select on public.luna_performance to authenticated;

create index if not exists luna_performance_pub_idx
  on public.luna_performance (publication_id, platform, measured_at desc);
