-- Strategy Lab + Agent : diffusion temps reel.
-- Les services VPS restent les producteurs ; l'application ne fait que lire.

do $$
begin
  alter publication supabase_realtime add table public.lab_status;
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  alter publication supabase_realtime add table public.lab_strategies;
exception
  when duplicate_object then null;
end
$$;

-- Journal persistant des recherches qui alimentent les hypotheses du Lab.
create table if not exists public.lab_research (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  sujet text not null,
  mode text not null default 'complet',
  famille text not null default 'inconnu',
  titre text not null default '',
  url text not null default '',
  hypothese text not null default '',
  conditions text not null default '',
  statut text not null default 'IDEATED'
);

alter table public.lab_research enable row level security;

drop policy if exists "lab research lecture" on public.lab_research;
create policy "lab research lecture" on public.lab_research
  for select to authenticated using (true);

do $$
begin
  alter publication supabase_realtime add table public.lab_research;
exception
  when duplicate_object then null;
end
$$;

comment on table public.lab_research is
  'Pistes de recherche du Strategy Lab. Une source est une piste, jamais une preuve ; toute hypothese doit etre testee hors echantillon.';
