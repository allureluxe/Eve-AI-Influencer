-- Historique complet des executions du compte reel.
-- Source: data/trades.jsonl, journal d'execution du robot.
-- Les signals restent la source riche des clotures recentes; cette table
-- conserve aussi les executions historiques qui n'ont jamais ete publiees.
create table if not exists public.alluxe_bot_historique_reel (
  trade_id       text primary key,
  reference      text not null,
  pair           text not null,
  side           text not null,
  entry_price    numeric(20,10) not null,
  exit_price     numeric(20,10) not null,
  volume         numeric(30,12) not null,
  opened_at      timestamptz not null,
  closed_at      timestamptz not null,
  profit_eur     numeric(20,8) not null default 0,
  result_pct     numeric(12,6),
  reason         text,
  partial        boolean not null default false,
  updated_at     timestamptz not null default now()
);

create index if not exists alluxe_bot_historique_reel_closed_idx
  on public.alluxe_bot_historique_reel (closed_at desc);

alter table public.alluxe_bot_historique_reel enable row level security;
alter table public.alluxe_bot_historique_reel force row level security;

drop policy if exists "alluxe bot historique reel : lecture admin"
  on public.alluxe_bot_historique_reel;
create policy "alluxe bot historique reel : lecture admin"
  on public.alluxe_bot_historique_reel for select
  to authenticated
  using (exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and p.is_admin
  ));

revoke all on public.alluxe_bot_historique_reel from anon, authenticated;
grant select on public.alluxe_bot_historique_reel to authenticated;
