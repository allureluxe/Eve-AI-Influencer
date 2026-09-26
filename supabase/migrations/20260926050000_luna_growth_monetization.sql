-- Luna : strategy growth + monetisation.
-- Les champs restent generiques afin de pouvoir faire evoluer les reseaux
-- sans casser luna_publications.

alter table public.luna_publications
  add column if not exists content_format text not null default 'legacy',
  add column if not exists platform text not null default 'instagram',
  add column if not exists scheduled_at timestamptz,
  add column if not exists timezone text not null default 'Europe/Paris',
  add column if not exists location_name text,
  add column if not exists location_city text,
  add column if not exists location_type text,
  add column if not exists highlight_name text,
  add column if not exists hook text,
  add column if not exists call_to_action text,
  add column if not exists hashtags text[] not null default '{}',
  add column if not exists ai_disclosure boolean not null default true,
  add column if not exists monetization_track text not null default 'growth',
  add column if not exists strategy_version text not null default '2026-09',
  add column if not exists source_job text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_content_format_chk') then
    alter table public.luna_publications add constraint luna_publications_content_format_chk
      check (content_format in (
        'legacy','feed_photo','story','highlight_story','reel',
        'tiktok_short','tiktok_rewards','tiktok_photo'
      ));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_platform_chk') then
    alter table public.luna_publications add constraint luna_publications_platform_chk
      check (platform in ('instagram','tiktok','both'));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_location_type_chk') then
    alter table public.luna_publications add constraint luna_publications_location_type_chk
      check (location_type is null or location_type in (
        'restaurant','bar','cafe','hotel','landmark','street','travel','other'
      ));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_monetization_chk') then
    alter table public.luna_publications add constraint luna_publications_monetization_chk
      check (monetization_track in (
        'growth','instagram_gifts','instagram_subscriptions',
        'tiktok_creator_rewards','tiktok_series','brand_deals'
      ));
  end if;
end $$;

create index if not exists luna_publications_schedule_idx
  on public.luna_publications (scheduled_at asc, statut);

create index if not exists luna_publications_platform_idx
  on public.luna_publications (platform, content_format, created_at desc);

comment on column public.luna_publications.content_format is
  'Format editorial : feed_photo, story, highlight_story, reel, tiktok_short, tiktok_rewards ou tiktok_photo.';
comment on column public.luna_publications.platform is
  'Plateforme cible : Instagram, TikTok, ou les deux.';
comment on column public.luna_publications.scheduled_at is
  'Heure de publication planifiee. NULL = publication immediate apres generation.';
comment on column public.luna_publications.highlight_name is
  'Nom du Highlight Instagram auquel la story doit etre rattachee manuellement si l API officielle ne le permet pas.';
comment on column public.luna_publications.ai_disclosure is
  'Doit rester true pour le contenu photorealiste genere par IA.';
comment on column public.luna_publications.monetization_track is
  'Objectif de la publication ; ce n est pas une promesse d eligibilite ou de revenus.';
