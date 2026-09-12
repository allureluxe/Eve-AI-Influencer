-- =====================================================================
--  PROFILES : un profil par compte
-- =====================================================================

create table public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  tier          user_tier  not null default 'free',
  risk_level    risk_level not null default 'normal',

  push_token    text,
  notif_signals boolean not null default true,
  notif_macro   boolean not null default true
);

comment on table public.profiles is
  'Un profil par compte. `tier` n''est PAS modifiable par l''utilisateur '
  '(voir la politique RLS) : ce serait s''offrir l''abonnement.';

create trigger profiles_touch
  before update on public.profiles
  for each row execute function public.touch_updated_at();

-- L'envoi des notifications part de la : « tous les jetons des comptes
-- qui veulent les signaux ».
create index profiles_push_signals_idx
  on public.profiles (tier)
  where push_token is not null and notif_signals;


-- ------------------------------------------------- creation automatique
--  LE PROFIL NAIT AVEC LE COMPTE.
--
--  Le laisser a la charge de l'application signifie qu'un plantage entre
--  l'inscription et le premier ecran laisse un compte sans profil : plus
--  aucune preference, et une application qui echoue sur un `null`. La
--  base le garantit, l'application n'a rien a faire.
create or replace function public.creer_profil_au_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id) values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger creer_profil_apres_inscription
  after insert on auth.users
  for each row execute function public.creer_profil_au_signup();


-- =====================================================================
--  SIGNAL_TAKEN : « j'ai pris ce trade »
-- =====================================================================

create table public.signal_taken (
  user_id   uuid not null references auth.users (id)   on delete cascade,
  signal_id uuid not null references public.signals (id) on delete cascade,
  taken_at  timestamptz not null default now(),

  -- Un utilisateur prend un signal UNE fois. Sans cette clef, un double
  -- appui sur le bouton creerait deux lignes et fausserait le compte des
  -- trades suivis.
  primary key (user_id, signal_id)
);

comment on table public.signal_taken is
  'Marquage « trade pris ». Chaque utilisateur ne voit que ses lignes.';

-- « Combien de personnes ont pris ce signal » : sans cet index, la
-- lecture par signal balaie toute la table.
create index signal_taken_par_signal_idx on public.signal_taken (signal_id);
