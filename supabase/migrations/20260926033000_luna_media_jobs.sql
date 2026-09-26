-- Luna : contrat media pilote par Claude / agent Alluxe.
-- Cette migration ajoute un contrat structure pour photo/video sans casser
-- les anciennes demandes texte de l'application.

alter table public.luna_publications
  add column if not exists media_type text not null default 'auto',
  add column if not exists reference_path text,
  add column if not exists aspect_ratio text not null default '3:4',
  add column if not exists duration_seconds int not null default 10,
  add column if not exists quality text not null default 'finale',
  add column if not exists provider text,
  add column if not exists provider_task_id text,
  add column if not exists generation_status text not null default 'queued',
  add column if not exists publish_requested boolean not null default false,
  add column if not exists published_at timestamptz,
  add column if not exists published_platform text,
  add column if not exists published_media_id text,
  add column if not exists updated_at timestamptz not null default now();

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_media_type_chk') then
    alter table public.luna_publications add constraint luna_publications_media_type_chk
      check (media_type in ('auto', 'photo', 'video'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_aspect_ratio_chk') then
    alter table public.luna_publications add constraint luna_publications_aspect_ratio_chk
      check (aspect_ratio in ('1:1', '3:4', '4:5', '2:3', '3:2', '4:3', '9:16', '16:9'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_duration_chk') then
    alter table public.luna_publications add constraint luna_publications_duration_chk
      check (duration_seconds between 1 and 30);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_quality_chk') then
    alter table public.luna_publications add constraint luna_publications_quality_chk
      check (quality in ('brouillon', 'finale'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_generation_status_chk') then
    alter table public.luna_publications add constraint luna_publications_generation_status_chk
      check (generation_status in ('queued', 'generating', 'succeeded', 'failed'));
  end if;
end $$;

comment on column public.luna_publications.media_type is
  'auto = ancien pipeline texte/photo/voix/video ; photo/video = job pilote par Claude.';
comment on column public.luna_publications.reference_path is
  'Chemin Supabase Storage ou ressource locale servant de reference media.';
comment on column public.luna_publications.publish_requested is
  'Intention explicite de publication ; aucune publication sans true.';
comment on column public.luna_publications.provider_task_id is
  'Identifiant de tache distante (ex. fournisseur image->video).';
comment on column public.luna_publications.generation_status is
  'Etat interne du media : queued, generating, succeeded, failed.';

create index if not exists luna_publications_media_queue_idx
  on public.luna_publications (statut, generation_status, created_at asc);

drop policy if exists "luna publications : creation admin uniquement"
  on public.luna_publications;

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
    and media_type = 'auto'
    and reference_path is null
    and aspect_ratio = '3:4'
    and duration_seconds = 10
    and quality = 'finale'
    and provider is null
    and provider_task_id is null
    and generation_status = 'queued'
    and publish_requested = false
    and published_at is null
    and published_platform is null
    and published_media_id is null
  );

revoke all on public.luna_publications from anon, authenticated;
grant select, insert on public.luna_publications to authenticated;
