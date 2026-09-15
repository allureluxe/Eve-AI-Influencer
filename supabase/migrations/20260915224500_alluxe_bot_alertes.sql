-- ============================================================
--  Alertes du robot pour Alluxe Bot -- remplace Telegram.
--
--  Meme contenu que ce que TelegramChannel envoie deja (voir
--  gold_bot/notifiers.py) : ouverture/fermeture de position, arret du
--  robot, problemes reels. Table privee comme alluxe_bot_prive (lecture
--  reservee aux comptes is_admin), ecrite par service_role.
-- ============================================================

create table public.alluxe_bot_alertes (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  niveau     text        not null check (niveau in ('debug','info','trade','warning','critical')),
  titre      text        not null,
  corps      text        not null default '',
  donnees    jsonb       not null default '{}'
);

comment on table public.alluxe_bot_alertes is
  'Alertes du robot (remplace Telegram) pour Alluxe Bot. Ecrit par '
  'service_role via gold_bot/notifiers.py::AlluxeBotChannel. Lecture '
  'reservee aux comptes admin.';

alter table public.alluxe_bot_alertes enable row level security;
alter table public.alluxe_bot_alertes force row level security;

create policy "alertes alluxe bot : lecture admin uniquement"
  on public.alluxe_bot_alertes for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

revoke all on public.alluxe_bot_alertes from anon, authenticated;
grant select on public.alluxe_bot_alertes to authenticated;

create index alluxe_bot_alertes_recentes_idx
  on public.alluxe_bot_alertes (created_at desc);

-- Garde les 500 dernieres alertes : suffisant pour un usage quotidien,
-- une table qui grossit sans fin degraderait la lecture pour rien.
create or replace function public.purger_vieilles_alertes()
returns trigger
language plpgsql
as $$
begin
  delete from public.alluxe_bot_alertes
  where id in (
    select id from public.alluxe_bot_alertes
    order by created_at desc
    offset 500
  );
  return null;
end;
$$;

create trigger alluxe_bot_alertes_purge
  after insert on public.alluxe_bot_alertes
  for each statement execute function public.purger_vieilles_alertes();
