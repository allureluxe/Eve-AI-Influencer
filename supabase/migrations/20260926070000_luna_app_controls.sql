-- Luna : autorise l'application admin a deposer des jobs medias et editoriaux.
--
-- Le telephone peut choisir le format, la plateforme, le planning et
-- demander la publication. Les champs de resultat restent inchangables
-- depuis le client : seuls les workers service_role les completent.

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
    and generation_status = 'queued'
    and provider_task_id is null
    and published_at is null
    and published_platform is null
    and published_media_id is null
    and media_type in ('auto', 'photo', 'video')
    and quality in ('brouillon', 'finale')
    and content_format in (
      'legacy','feed_photo','story','highlight_story','reel',
      'tiktok_short','tiktok_rewards','tiktok_photo'
    )
    and platform in ('instagram','tiktok','both')
    and location_type is null or location_type in (
      'restaurant','bar','cafe','hotel','landmark','street','travel','other'
    )
    and monetization_track in (
      'growth','instagram_gifts','instagram_subscriptions',
      'tiktok_creator_rewards','tiktok_series','brand_deals'
    )
  );

-- Corrige la precedence SQL du check location_type ci-dessus sans retirer
-- les autres contraintes : une policy ne doit jamais autoriser un job
-- dont le type de lieu est invalide.
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
    and generation_status = 'queued'
    and provider_task_id is null
    and published_at is null
    and published_platform is null
    and published_media_id is null
    and media_type in ('auto', 'photo', 'video')
    and quality in ('brouillon', 'finale')
    and content_format in (
      'legacy','feed_photo','story','highlight_story','reel',
      'tiktok_short','tiktok_rewards','tiktok_photo'
    )
    and platform in ('instagram','tiktok','both')
    and (location_type is null or location_type in (
      'restaurant','bar','cafe','hotel','landmark','street','travel','other'
    ))
    and monetization_track in (
      'growth','instagram_gifts','instagram_subscriptions',
      'tiktok_creator_rewards','tiktok_series','brand_deals'
    )
  );

revoke all on public.luna_publications from anon, authenticated;
grant select, insert on public.luna_publications to authenticated;
