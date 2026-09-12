-- =====================================================================
--  ECONOMIC_EVENTS : l'agenda economique
-- =====================================================================

create table public.economic_events (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  event_time  timestamptz  not null,
  name_fr     text         not null check (length(btrim(name_fr)) > 0),
  -- Code ISO a deux lettres, ou 'EU' / 'XX' pour le monde. Contraint
  -- parce qu'un melange « US », « USA », « Etats-Unis » rendrait tout
  -- filtrage par pays inutilisable des la deuxieme source de donnees.
  country     char(2)      not null check (country ~ '^[A-Z]{2}$'),
  impact      event_impact not null,

  -- Ce qu'Eve FAIT autour de cet evenement, en francais et a la premiere
  -- personne : « je n'ouvre rien 20 minutes avant et apres ». C'est la
  -- promesse affichee a l'utilisateur, pas un commentaire interne.
  eve_policy  text,

  -- Nuls tant que l'annonce n'est pas tombee.
  actual      numeric(18,4),
  forecast    numeric(18,4),
  previous    numeric(18,4),

  -- UNE ANNONCE N'EXISTE QU'UNE FOIS. Deux sources de calendrier
  -- publieront le meme CPI ; sans cette clef l'application afficherait
  -- l'evenement en double et le robot le compterait deux fois.
  constraint evenement_unique unique (event_time, country, name_fr)
);

comment on column public.economic_events.eve_policy is
  'Ce que le robot fait autour de l''annonce, en francais, affiche tel quel.';

create trigger economic_events_touch
  before update on public.economic_events
  for each row execute function public.touch_updated_at();

--  L'agenda se lit toujours « a partir de maintenant », et l'ecran
--  d'accueil ne montre que le fort impact.
create index economic_events_a_venir_idx on public.economic_events (event_time);
create index economic_events_impact_idx
  on public.economic_events (event_time)
  where impact = 'high';


-- =====================================================================
--  MARKET_NOTES : l'analyse quotidienne
-- =====================================================================

create table public.market_notes (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  published_at    timestamptz,          -- NULL = brouillon, comme signals
  headline        text not null check (length(btrim(headline)) > 0),
  body_fr         text not null check (length(btrim(body_fr)) >= 40),

  -- Indicateurs affiches en jauges. Bornes contraintes : une jauge qui
  -- recoit 250 sur 100 s'affiche hors de son cadre, et personne ne le
  -- voit venir avant la capture d'ecran d'un utilisateur.
  trend_score     smallint check (trend_score      between -100 and 100),
  volatility_score smallint check (volatility_score between 0 and 100),
  fear_greed      smallint check (fear_greed       between 0 and 100),
  btc_dominance   numeric(5,2) check (btc_dominance between 0 and 100)
);

comment on column public.market_notes.trend_score is
  'De -100 (baissier franc) a +100 (haussier franc).';

create trigger market_notes_touch
  before update on public.market_notes
  for each row execute function public.touch_updated_at();

create index market_notes_publiees_idx
  on public.market_notes (published_at desc)
  where published_at is not null;
