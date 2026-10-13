-- Liste d'e-mails d'alluxe.fr (13 oct. 2026) : « préviens-moi à l'ouverture des
-- commandes / des nouveautés ». Reçue par la fonction alluxe-site-inscription.
-- Lue par l'opérateur seulement : RLS sans aucune politique, seule la clé de service écrit.
-- Une adresse n'apparaît qu'une fois ; desinscrit_le rempli = ne plus jamais écrire.
create table if not exists public.alluxe_site_inscrits (
  id             bigserial primary key,
  cree_le        timestamptz not null default now(),
  email          text not null unique,
  interet        text not null default 'tout',   -- noel | livres | offres | tout
  page           text,                           -- la page où l'inscription a eu lieu
  desinscrit_le  timestamptz
);
alter table public.alluxe_site_inscrits enable row level security;
