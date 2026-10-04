-- Les commandes passées depuis alluxe.fr (page commander.html), reçues par
-- la fonction alluxe-site-demande. Lues par l'opérateur (et son agent),
-- jamais par le public : RLS sans aucune politique, seule la clé de service écrit.
create table if not exists public.alluxe_site_demandes (
  id          bigserial primary key,
  cree_le     timestamptz not null default now(),
  offre       text not null,
  formule     text not null,
  nom         text not null,
  email       text not null,
  telephone   text,
  activite    text,
  message     text,
  statut      text not null default 'nouvelle'   -- nouvelle | rappelee | acceptee | refusee
);
alter table public.alluxe_site_demandes enable row level security;
