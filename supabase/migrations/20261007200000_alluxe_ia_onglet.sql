-- Onglet « alluxe.ia » de l'appli Alluxe Bot (7 oct. 2026) : remplace l'onglet Luna.
--
--   alluxe_ia_compte     : chiffres du compte par réseau (abonnés, portée 7 j...)
--   alluxe_ia_medias     : chaque post / Reel publié, avec ses statistiques
--   alluxe_ia_cibles     : la liste du jour « à commenter » (assistant commentaires)
--   alluxe_ia_a_publier  : les Reels préparés que l'opérateur publie depuis son téléphone
--
-- Écrits par les scripts du serveur (service_role). L'appli LIT, et ne peut
-- changer QUE le statut d'une cible ou d'un Reel à publier (« fait », « publié »).
-- Lecture réservée aux admins : la même base sert l'appli publique Allure.

create table if not exists public.alluxe_ia_compte (
  reseau text primary key,
  abonnes integer,
  publications integer,
  portee_7j integer,
  vues_7j integer,
  visites_profil_7j integer,
  clics_site_7j integer,
  maj_le timestamptz not null default now()
);

create table if not exists public.alluxe_ia_medias (
  media_id text primary key,
  reseau text not null default 'instagram',
  type text,                       -- REEL, CARROUSEL, PHOTO
  legende text,
  lien text,
  vignette text,
  publie_le timestamptz,
  portee integer, vues integer, likes integer, commentaires integer,
  enregistrements integer, partages integer,
  duree_moyenne_s numeric, duree_video_s numeric,
  maj_le timestamptz not null default now()
);
create index if not exists alluxe_ia_medias_recents_idx on public.alluxe_ia_medias (publie_le desc);

create table if not exists public.alluxe_ia_cibles (
  id uuid primary key default gen_random_uuid(),
  jour date not null default (now() at time zone 'Europe/Paris')::date,
  lien text not null unique,
  compte text,
  legende text,
  likes integer, commentaires integer,
  publie_le timestamptz,
  hashtag text,
  commentaire_propose text,
  statut text not null default 'a_faire' check (statut in ('a_faire', 'fait', 'ignore')),
  cree_le timestamptz not null default now()
);
create index if not exists alluxe_ia_cibles_jour_idx on public.alluxe_ia_cibles (jour desc);

create table if not exists public.alluxe_ia_a_publier (
  id text primary key,             -- ex. 05-ia-en-double:tiktok
  titre text not null,
  reseau text not null default 'instagram',
  chemin_video text,               -- chemin dans le seau privé « luna »
  legende text,
  musique text,
  statut text not null default 'a_publier' check (statut in ('a_publier', 'publie')),
  cree_le timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['alluxe_ia_compte', 'alluxe_ia_medias', 'alluxe_ia_cibles', 'alluxe_ia_a_publier'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('drop policy if exists "%s : lecture admin" on public.%I', t, t);
    execute format($p$create policy "%s : lecture admin" on public.%I for select to authenticated
      using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.is_admin))$p$, t, t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
  end loop;
end $$;

-- Seul le statut peut être changé depuis l'appli, et seulement par un admin.
drop policy if exists "alluxe_ia_cibles : statut admin" on public.alluxe_ia_cibles;
create policy "alluxe_ia_cibles : statut admin" on public.alluxe_ia_cibles for update to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.is_admin))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.is_admin));
grant update (statut) on public.alluxe_ia_cibles to authenticated;

drop policy if exists "alluxe_ia_a_publier : statut admin" on public.alluxe_ia_a_publier;
create policy "alluxe_ia_a_publier : statut admin" on public.alluxe_ia_a_publier for update to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.is_admin))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.is_admin));
grant update (statut) on public.alluxe_ia_a_publier to authenticated;
