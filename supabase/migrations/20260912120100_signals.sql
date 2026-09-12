-- =====================================================================
--  SIGNALS : les signaux publies par le robot
-- =====================================================================

create table public.signals (
  id                uuid primary key default gen_random_uuid(),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  -- BROUILLON TANT QUE C'EST NUL. Le robot peut inserer un signal en
  -- preparation ; il n'apparait dans l'application qu'une fois cette date
  -- posee. Sans ce garde-fou, un signal en cours de calcul serait visible
  -- une fraction de seconde — et un utilisateur qui le suit entrerait sur
  -- des niveaux qui bougent encore.
  published_at      timestamptz,

  pair              text        not null check (pair ~ '^[A-Z0-9]{2,12}/[A-Z]{3,5}$'),
  side              signal_side not null,

  entry_price       numeric(20,10) not null check (entry_price > 0),
  stop_loss         numeric(20,10) not null check (stop_loss  > 0),
  take_profit_1     numeric(20,10) check (take_profit_1 > 0),
  take_profit_2     numeric(20,10) check (take_profit_2 > 0),

  risk_reward       numeric(8,2)  check (risk_reward >= 0),
  position_size_pct numeric(6,3)  check (position_size_pct > 0 and position_size_pct <= 100),
  conviction        smallint      not null check (conviction between 0 and 100),

  rationale         text not null check (length(btrim(rationale)) >= 20),

  status            signal_status not null default 'active',
  closed_at         timestamptz,
  result_pct        numeric(8,3),

  -- Le signal traverse-t-il une annonce a fort impact ? Renseigne par le
  -- robot au moment de publier, a partir de `economic_events`.
  macro_flag        boolean not null default false,

  -- LE STOP EST DU BON COTE, ET LA BASE LE VERIFIE.
  --
  -- Un stop place au-dessus du prix d'entree sur un achat n'est pas un
  -- reglage discutable : c'est une erreur qui declenche la vente
  -- immediatement. La contrainte coute zero et rend le cas impossible.
  constraint stop_du_bon_cote check (
    (side = 'buy'  and stop_loss < entry_price) or
    (side = 'sell' and stop_loss > entry_price)
  ),
  constraint objectifs_du_bon_cote check (
    take_profit_1 is null or
    (side = 'buy'  and take_profit_1 > entry_price) or
    (side = 'sell' and take_profit_1 < entry_price)
  ),
  -- Un signal clos porte une date de cloture, un signal actif n'en porte
  -- pas. Les deux incoherences faussent les statistiques en silence.
  constraint cloture_coherente check (
    (status in ('closed_tp','closed_sl','cancelled') and closed_at is not null)
    or (status = 'active' and closed_at is null)
  )
);

comment on table  public.signals is
  'Signaux du robot Turtle. Ecriture reservee a service_role.';
comment on column public.signals.published_at is
  'NULL = brouillon, invisible de l''application. Voir la politique RLS.';
comment on column public.signals.rationale is
  'Explication en francais, telle qu''affichee a l''utilisateur.';

create trigger signals_touch
  before update on public.signals
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------- index
--  L'ecran d'accueil demande « les signaux publies, les plus recents
--  d'abord ». Sans cet index c'est un balayage complet a chaque
--  ouverture de l'application.
create index signals_publies_idx
  on public.signals (published_at desc)
  where published_at is not null;

--  L'onglet « en cours » filtre sur le statut.
create index signals_actifs_idx
  on public.signals (status, published_at desc)
  where published_at is not null;

create index signals_paire_idx on public.signals (pair, published_at desc);
