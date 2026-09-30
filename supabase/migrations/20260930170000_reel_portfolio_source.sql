-- Source de verite du mode Reel : portefeuille Bitvavo, pas les signaux publies.
alter table public.alluxe_bot_comptes
  add column if not exists cash_eur numeric(12,2),
  add column if not exists positions_reel jsonb not null default '[]'::jsonb;

comment on column public.alluxe_bot_comptes.cash_eur is
  'Euros réellement disponibles sur Bitvavo au dernier battement.';
comment on column public.alluxe_bot_comptes.positions_reel is
  'Portefeuille réel Bitvavo réconcilié avec les prix d entrée du robot; source de vérité des positions affichées en mode Reel.';
