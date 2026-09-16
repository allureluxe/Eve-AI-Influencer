-- ============================================================
--  Alluxe -- le 4e bouton : l'agent personnel.
--
--  PREMIERE VERSION, DELIBEREMENT LIMITEE A LA LECTURE. L'operateur a
--  demande un agent "qui repond et qui agit" -- avant de lui donner un
--  quelconque pouvoir d'action (redemarrer le robot, changer un
--  reglage...), cette version ne fait que REPONDRE, en lisant les
--  memes tables que le reste de l'application (etat_public,
--  alluxe_bot_prive, alluxe_bot_alertes, luna_persona,
--  luna_publications). Aucune ecriture, aucune commande shell, aucun
--  acces direct au depot. Donner un pouvoir d'action est une decision
--  distincte, avec ses propres garde-fous (confirmation, journal,
--  perimetre precis) -- a prendre explicitement avec l'operateur.
--
--  Meme principe de file que Luna : l'app INSERE un message (role
--  'user'), un service sur le VPS (`ops/agent_alluxe.py`, PAS un cron
--  -- une conversation ne peut pas attendre 2 minutes entre deux
--  phrases) le lit et insere la reponse (role 'assistant'). La RLS
--  empeche l'app de deposer une reponse a la place de l'agent.
-- ============================================================

create table public.alluxe_agent_messages (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  role       text        not null check (role in ('user', 'assistant')),
  contenu    text        not null default '',
  traite     boolean     not null default false,
  outils     jsonb       not null default '[]'
);

comment on table public.alluxe_agent_messages is
  'Conversation avec Alluxe (agent personnel, tab 4). `traite=false` '
  'sur un message `user` signale a ops/agent_alluxe.py qu''il attend '
  'une reponse -- reclame de facon atomique comme luna_publications. '
  '`outils` liste les outils de lecture appeles pour construire une '
  'reponse `assistant` (transparence : quelles donnees ont ete lues).';

alter table public.alluxe_agent_messages enable row level security;
alter table public.alluxe_agent_messages force row level security;

create policy "agent alluxe : lecture admin uniquement"
  on public.alluxe_agent_messages for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

-- L'app ne peut deposer qu'un message `user`, non marque traite, sans
-- outils -- exactement comme luna_publications verrouille ses colonnes
-- de resultat : seul service_role peut ecrire une reponse `assistant`.
create policy "agent alluxe : message utilisateur uniquement"
  on public.alluxe_agent_messages for insert
  to authenticated
  with check (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
    and role = 'user' and traite = false and outils = '[]'::jsonb
  );

revoke all on public.alluxe_agent_messages from anon, authenticated;
grant select, insert on public.alluxe_agent_messages to authenticated;

create index alluxe_agent_messages_recents_idx
  on public.alluxe_agent_messages (created_at desc);

-- Garde les 300 derniers messages -- une conversation avec un seul
-- operateur n'a pas besoin d'un historique illimite, meme principe que
-- la purge d'alluxe_bot_alertes.
create or replace function public.purger_vieux_messages_agent()
returns trigger
language plpgsql
as $$
begin
  delete from public.alluxe_agent_messages
  where id in (
    select id from public.alluxe_agent_messages
    order by created_at desc
    offset 300
  );
  return null;
end;
$$;

create trigger alluxe_agent_messages_purge
  after insert on public.alluxe_agent_messages
  for each statement execute function public.purger_vieux_messages_agent();
