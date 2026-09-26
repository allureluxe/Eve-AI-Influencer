-- Suivi des publications multi-plateformes et des Stories a conserver.
alter table public.luna_publications
  add column if not exists publication_task_id text,
  add column if not exists publication_status text not null default 'not_requested',
  add column if not exists highlight_status text not null default 'not_requested';

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_publication_status_chk') then
    alter table public.luna_publications add constraint luna_publications_publication_status_chk
      check (publication_status in ('not_requested','pending','published','failed'));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_highlight_status_chk') then
    alter table public.luna_publications add constraint luna_publications_highlight_status_chk
      check (highlight_status in ('not_requested','pending_manual','saved'));
  end if;
end $$;

comment on column public.luna_publications.publication_task_id is
  'Identifiant de publication asynchrone du reseau cible, distinct du job de generation media.';
comment on column public.luna_publications.publication_status is
  'Etat de diffusion du contenu sur le reseau cible.';
comment on column public.luna_publications.highlight_status is
  'Pour les Stories Instagram : saved lorsque le contenu est effectivement ajoute a un Highlight.';

create index if not exists luna_publications_publication_pending_idx
  on public.luna_publications (publication_status, publish_requested, created_at asc);
