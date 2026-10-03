-- alluxe.ia : le robot KIT (decision de l'operateur, 3 oct. 2026).
--
-- Quelqu'un commente KIT sous un post -> il recoit le kit en message prive.
--
-- La fonction `alluxe-ia-webhook` ne fait que DEPOSER ce qu'Instagram lui
-- envoie ici. C'est le VPS (`ops/alluxe_ia_kit.py traiter`) qui repond,
-- avec le jeton Instagram de son .env : aucun jeton Instagram ne vit dans
-- Supabase, donc aucun ne peut y expirer en silence.
--
-- Aucune politique RLS : ni l'application ni la cle anon n'ont a lire
-- les messages prives des gens. Seul service_role y touche.

create table if not exists public.alluxe_ia_evenements (
  id          bigserial primary key,
  -- id du commentaire, ou mid du message : Instagram renvoie parfois le
  -- meme evenement deux fois, l'unicite empeche de repondre deux fois.
  ident       text not null unique,
  type        text not null check (type in ('commentaire', 'message')),
  ig_user_id  text not null,
  username    text,
  texte       text,
  media_id    text,
  recu_at     timestamptz not null default now(),
  traite_at   timestamptz,
  resultat    text,
  tentatives  int not null default 0
);

create index if not exists alluxe_ia_evenements_a_traiter
  on public.alluxe_ia_evenements (recu_at) where traite_at is null;

-- Ou en est chaque personne dans la sequence (prompt n°6 du concept).
create table if not exists public.alluxe_ia_contacts (
  ig_user_id      text primary key,
  username        text,
  kit_envoye_at   timestamptz,
  -- 1 = kit envoye, 2 = qualification envoyee, 3 = offre envoyee
  etape           int not null default 0,
  profil          text check (profil in ('zero', 'commence')),
  derniere_reponse_at timestamptz,
  maj_at          timestamptz not null default now()
);

alter table public.alluxe_ia_evenements enable row level security;
alter table public.alluxe_ia_contacts enable row level security;
revoke all on public.alluxe_ia_evenements from anon, authenticated;
revoke all on public.alluxe_ia_contacts from anon, authenticated;
revoke all on sequence public.alluxe_ia_evenements_id_seq from anon, authenticated;
