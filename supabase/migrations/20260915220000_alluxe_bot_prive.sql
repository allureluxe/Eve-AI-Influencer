-- ============================================================
--  Donnees privees pour l'application Alluxe Bot (outil interne de
--  l'operateur, distinct d'Allure).
--
--  Contrairement a `signals`/`etat_public`, cette table n'est PAS
--  destinee a tout utilisateur connecte : seul un compte marque
--  `is_admin` peut la lire. `signals` donne deja les positions/
--  l'historique (RLS permissive existante, reutilisee par Alluxe Bot
--  directement) ; cette table-ci porte ce qui n'existe encore nulle
--  part -- l'echantillon des 40 trades de preuve et la progression
--  vers les objectifs de croissance (3 000 / 10 000 / 50 000 EUR).
--
--  Une seule ligne (id fixe 'robot'), meme principe que `etat_public`.
--  Ecrite par un script sur le VPS (service_role), jamais par l'app.
-- ============================================================

alter table public.profiles add column if not exists is_admin boolean not null default false;

comment on column public.profiles.is_admin is
  'Acces aux donnees privees d''Alluxe Bot (pas Allure). Positionne '
  'a la main, jamais depuis l''application.';

create table public.alluxe_bot_prive (
  id          text primary key,
  stats_40    jsonb       not null default '{}',
  objectifs   jsonb       not null default '{}',
  methode     text        not null default '',
  updated_at  timestamptz not null default now()
);

comment on table public.alluxe_bot_prive is
  'Statistiques privees du robot (echantillon de preuve, objectifs de '
  'croissance) pour Alluxe Bot. Ecrit uniquement par service_role via '
  'ops/publier_alluxe_bot_prive.py. Lecture reservee aux comptes admin.';

alter table public.alluxe_bot_prive enable row level security;
alter table public.alluxe_bot_prive force row level security;

create policy "alluxe bot prive : lecture admin uniquement"
  on public.alluxe_bot_prive for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

revoke all on public.alluxe_bot_prive from anon, authenticated;
grant select on public.alluxe_bot_prive to authenticated;
