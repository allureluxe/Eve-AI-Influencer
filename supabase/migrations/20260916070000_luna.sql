-- ============================================================
--  Luna -- interface mobile (tab 3 d'Alluxe Bot).
--
--  Meme principe de confidentialite que alluxe_bot_prive/alertes :
--  lecture reservee aux comptes is_admin. Deux nouveautes par rapport
--  aux tables precedentes :
--
--  1. `luna_publications` accepte aussi une ECRITURE depuis
--     l'application (insert) : c'est ainsi que l'operateur declenche
--     une nouvelle generation depuis son telephone -- il depose une
--     ligne `en_attente`, `ops/executer_luna.py` (cron, VPS) la prend
--     en charge et la complete. Aucun acces direct au VPS depuis
--     l'app, meme principe que le reste (tout passe par Supabase).
--  2. Un bucket de stockage prive `luna` pour les photos/voix/videos
--     generees -- premier bucket du depot, RLS calquee sur la table.
-- ============================================================

create table public.luna_persona (
  id         text primary key,
  prenom     text        not null default '',
  age        int         not null default 0,
  metier     text        not null default '',
  contexte   text        not null default '',
  caractere  jsonb       not null default '[]',
  passions   jsonb       not null default '[]',
  updated_at timestamptz not null default now()
);

comment on table public.luna_persona is
  'Description du personnage Luna (luna/persona.py), republiee a '
  'chaque tour d''ops/executer_luna.py -- une seule ligne (id fixe '
  '''luna''). Lecture reservee aux comptes admin, meme principe que '
  'alluxe_bot_prive.';

alter table public.luna_persona enable row level security;
alter table public.luna_persona force row level security;

create policy "luna persona : lecture admin uniquement"
  on public.luna_persona for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

revoke all on public.luna_persona from anon, authenticated;
grant select on public.luna_persona to authenticated;


create table public.luna_publications (
  id            uuid        primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  demande       text        not null default '',
  statut        text        not null default 'en_attente'
                  check (statut in ('en_attente', 'en_cours', 'terminee', 'echec')),
  legende       text        not null default '',
  scene_prompt  text        not null default '',
  chemin_photo  text,
  chemin_voix   text,
  chemin_video  text,
  erreurs       jsonb       not null default '{}'
);

comment on table public.luna_publications is
  'File des generations de contenu Luna. L''app INSERE une ligne '
  '(demande, statut par defaut ''en_attente'') pour declencher une '
  'generation ; ops/executer_luna.py (service_role, VPS) la traite et '
  'complete legende/scene_prompt/chemins/erreurs. Lecture et creation '
  'reservees aux comptes admin -- seule la mise a jour est reservee au '
  'service_role, sinon l''app pourrait se pretendre "terminee" sans '
  'que rien n''ait ete genere.';

alter table public.luna_publications enable row level security;
alter table public.luna_publications force row level security;

create policy "luna publications : lecture admin uniquement"
  on public.luna_publications for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

-- Seule la demande de generation vient de l'app ; le reste (statut,
-- legende, chemins...) garde ses valeurs par defaut a l'insertion et
-- n'est ensuite modifiable QUE par service_role (aucune policy update
-- pour authenticated => update refuse par la RLS forcee).
create policy "luna publications : creation admin uniquement"
  on public.luna_publications for insert
  to authenticated
  with check (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
    and statut = 'en_attente'
    and legende = '' and scene_prompt = ''
    and chemin_photo is null and chemin_voix is null and chemin_video is null
    and erreurs = '{}'::jsonb
  );

revoke all on public.luna_publications from anon, authenticated;
grant select, insert on public.luna_publications to authenticated;

create index luna_publications_recentes_idx
  on public.luna_publications (created_at desc);


-- ---------------------------------------------------------- stockage

insert into storage.buckets (id, name, public)
values ('luna', 'luna', false)
on conflict (id) do nothing;

create policy "luna storage : lecture admin uniquement"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'luna'
    and exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

-- Pas de policy insert/update/delete pour authenticated : seul
-- service_role (ops/executer_luna.py, sur le VPS) depose des fichiers
-- -- il contourne la RLS, ce n'est donc pas une omission.
