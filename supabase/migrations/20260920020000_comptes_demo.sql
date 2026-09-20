-- ============================================================
--  La fiche de chaque compte de simulation -- 20 sept.
--
--  Demande de l'operateur : « dans l'application, 3 onglets dans le
--  mode demo — demo 1, demo 2, demo 3 — et le nom de la methode
--  utilisee avec le capital en direct en euros. En cliquant dessus
--  j'ai toutes les positions et l'historique du compte. »
--
--  L'application ne peut pas DEDUIRE la methode : elle ne lit pas
--  `robot.demo2.json`. Et elle ne doit surtout pas la recopier --
--  c'est exactement ce qui a fait afficher « canal 20 jours »
--  pendant une semaine alors que le robot tournait a 10.
--
--  Chaque robot publie donc SA fiche au demarrage, deduite de sa
--  propre configuration (`gold_bot/methode.py`). Un compte arrete
--  garde sa derniere fiche, avec `vu_le` qui dit quand il a parle
--  pour la derniere fois.
-- ============================================================

create table if not exists public.alluxe_bot_comptes (
  compte          text primary key,
  -- Trois mots, pour tenir sur un onglet. Deduit de la configuration,
  -- jamais ecrit a la main.
  resume_methode  text not null default '',
  -- La description complete, pour la fiche du compte.
  methode         text not null default '',
  capital_depart  numeric not null default 0,
  -- Horodatage du dernier signe de vie. L'application s'en sert pour
  -- dire « arrete depuis 3 h » au lieu d'afficher un capital fige
  -- comme s'il etait a jour.
  vu_le           timestamptz not null default now(),
  cree_le         timestamptz not null default now()
);

alter table public.alluxe_bot_comptes enable row level security;

drop policy if exists "comptes lecture" on public.alluxe_bot_comptes;
create policy "comptes lecture" on public.alluxe_bot_comptes
  for select to authenticated using (true);

-- L'application LIT, elle n'ecrit jamais : seuls les robots publient
-- leur fiche, en service_role. Une application qui pourrait ecrire ici
-- pourrait afficher une methode que personne ne fait tourner.

comment on table public.alluxe_bot_comptes is
  'Fiche de chaque compte de simulation : methode reellement armee '
  '(deduite de sa configuration), capital de depart, dernier signe de '
  'vie. Publiee par le robot lui-meme au demarrage.';
