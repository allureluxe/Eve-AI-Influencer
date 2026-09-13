-- ============================================================
--  Les notifications : une file d'attente, pas trois chemins
-- ============================================================
--
--  Trois exigences se ressemblent et se resolvent au meme endroit :
--
--    - un compte gratuit recoit le signal DEUX HEURES apres l'abonne ;
--    - rien ne part entre 23 h et 7 h dans le fuseau de l'utilisateur ;
--    - une notification ne doit jamais partir deux fois.
--
--  Les traiter separement — un envoi immediat ici, un `setTimeout` la,
--  un garde-fou ailleurs — donne trois codes qui se contredisent des
--  qu'un conteneur redemarre : le `setTimeout` disparait avec lui, et
--  l'utilisateur gratuit ne recoit jamais rien.
--
--  Une file d'attente rend les trois triviaux. Chaque notification est
--  une LIGNE avec une heure d'envoi calculee a l'avance. Un travailleur
--  passe toutes les cinq minutes et envoie ce qui est du. Un
--  redemarrage ne perd rien : la ligne est en base.

-- --------------------------------------------------- fuseau et nuit
alter table public.profiles
  add column timezone text not null default 'Europe/Paris',
  add column notif_nuit boolean not null default false;

comment on column public.profiles.timezone is
  'Fuseau IANA de l''utilisateur. Sert a calculer le silence 23h-7h.';
comment on column public.profiles.notif_nuit is
  'Seul un abonne peut l''activer, et seulement pour les signaux en '
  'temps reel. Par defaut la nuit est silencieuse.';

-- Un fuseau invalide ferait echouer tous les calculs d'heure de cet
-- utilisateur. On verifie a l'ecriture plutot qu'a chaque envoi.
alter table public.profiles
  add constraint fuseau_connu check (
    timezone is not null and now() at time zone timezone is not null
  ) not valid;

-- --------------------------------------------------------- la file
create type notif_kind as enum (
  'signal_nouveau',      -- un signal vient d'etre publie
  'evenement_macro',     -- annonce importante dans 15 minutes
  'signal_cloture'       -- un trade que l'utilisateur a marque est fini
);

create table public.notifications (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),

  user_id     uuid not null references auth.users(id) on delete cascade,
  kind        notif_kind not null,

  -- L'objet concerne : un signal ou un evenement. Avec `kind` et
  -- `user_id`, c'est la cle qui empeche le doublon.
  ref_id      uuid not null,

  title       text not null check (length(btrim(title)) > 0),
  body        text not null check (length(btrim(body)) > 0),

  -- QUAND ELLE DOIT PARTIR. Le report de deux heures du palier gratuit
  -- et le decalage de la nuit sont deja appliques ici : le travailleur
  -- n'a aucune regle a connaitre, il envoie ce qui est du.
  a_envoyer_a timestamptz not null,

  envoye_a    timestamptz,
  echecs      smallint not null default 0,
  -- Apres plusieurs echecs on abandonne : un jeton revoque (application
  -- desinstallee) ferait sinon boucler la file pour toujours.
  abandonne   boolean not null default false,

  constraint notification_unique unique (user_id, kind, ref_id)
);

comment on table public.notifications is
  'File d''attente des notifications push. Voir la migration '
  '20260913091000 pour pourquoi c''est une file et non trois chemins.';

--  Le travailleur ne lit que ca : ce qui est du et pas encore parti.
create index notifications_a_envoyer_idx
  on public.notifications (a_envoyer_a)
  where envoye_a is null and not abandonne;

-- ------------------------------------------------ interdiction de nuit
--
--  UNE FONCTION, PAS UNE REGLE RECOPIEE DANS CHAQUE APPELANT.
--
--  Rend l'heure d'envoi effective : celle demandee si elle tombe dans
--  la journee de l'utilisateur, sinon 7 h le matin suivant, dans SON
--  fuseau. Un abonne qui a explicitement accepte la nuit n'est pas
--  decale — c'est le seul cas, et il doit l'avoir demande.

create or replace function public.heure_dEnvoi_autorisee(
  souhaitee   timestamptz,
  fuseau      text,
  nuit_permise boolean default false
) returns timestamptz
language plpgsql
immutable
as $$
declare
  locale timestamp;
  heure  int;
begin
  if nuit_permise then
    return souhaitee;
  end if;

  begin
    locale := souhaitee at time zone fuseau;
  exception when others then
    -- Fuseau inconnu : on retombe sur Paris plutot que d'echouer.
    -- Une notification a la mauvaise heure vaut mieux qu'une
    -- notification jamais envoyee.
    locale := souhaitee at time zone 'Europe/Paris';
    fuseau := 'Europe/Paris';
  end;

  heure := extract(hour from locale);

  if heure >= 23 then
    -- Apres 23 h : 7 h le lendemain matin.
    return ((date_trunc('day', locale) + interval '1 day 7 hours')
            at time zone fuseau);
  elsif heure < 7 then
    -- Avant 7 h : 7 h le matin meme.
    return ((date_trunc('day', locale) + interval '7 hours')
            at time zone fuseau);
  end if;

  return souhaitee;
end;
$$;

comment on function public.heure_dEnvoi_autorisee is
  'Decale une notification hors de la plage 23h-7h du fuseau de '
  'l''utilisateur. Un abonne ayant accepte la nuit n''est pas decale.';

-- ------------------------------------------------------------- RLS
alter table public.notifications enable row level security;

--  L'utilisateur peut consulter son historique (ecran « notifications »).
--  Personne ne peut ecrire : seule la cle de service alimente la file.
create policy notifications_lecture_propre
  on public.notifications for select
  to authenticated
  using (user_id = auth.uid());
