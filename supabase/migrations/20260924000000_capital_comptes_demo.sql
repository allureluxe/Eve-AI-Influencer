-- Capital vivant et gain encaisse des comptes de simulation.
-- Ces colonnes sont publiees par run_demo.py / battement_comptes.py
-- et lues par l'application pour eviter toute reconstruction locale.

alter table public.alluxe_bot_comptes
  add column if not exists capital_eur numeric(12,2),
  add column if not exists encaisse_eur numeric(12,2);

comment on column public.alluxe_bot_comptes.capital_eur is
  'Equity vivante du simulateur : solde + gain/perte latent.';
comment on column public.alluxe_bot_comptes.encaisse_eur is
  'Variation du solde liquide depuis le capital de depart, frais compris.';
