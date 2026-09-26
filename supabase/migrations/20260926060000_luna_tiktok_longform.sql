-- TikTok long-form : les jobs Creator Rewards sont assembles a partir
-- de plusieurs clips originaux courts, car un fournisseur video unitaire
-- peut etre limite a 30 secondes.
alter table public.luna_publications
  add column if not exists segment_count int not null default 1,
  add column if not exists segment_duration_seconds int not null default 15,
  add column if not exists assembly_status text not null default 'not_required';

alter table public.luna_publications
  drop constraint if exists luna_publications_duration_chk;

alter table public.luna_publications
  add constraint luna_publications_duration_chk
  check (duration_seconds between 1 and 180);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'luna_publications_segment_count_chk') then
    alter table public.luna_publications add constraint luna_publications_segment_count_chk
      check (segment_count between 1 and 12);
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_segment_duration_chk') then
    alter table public.luna_publications add constraint luna_publications_segment_duration_chk
      check (segment_duration_seconds between 5 and 30);
  end if;

  if not exists (select 1 from pg_constraint where conname = 'luna_publications_assembly_status_chk') then
    alter table public.luna_publications add constraint luna_publications_assembly_status_chk
      check (assembly_status in ('not_required','collecting','assembled','failed'));
  end if;
end $$;

comment on column public.luna_publications.segment_count is
  'Nombre de clips necessaires pour assembler un TikTok long format.';
comment on column public.luna_publications.segment_duration_seconds is
  'Duree cible de chaque clip genere par le fournisseur video.';
comment on column public.luna_publications.assembly_status is
  'Etat de l assemblage local des clips en un fichier final.';
