-- ============================================================
--  Marque "demo" sur signals et alluxe_bot_alertes -- 18 sept.
--
--  Trouve le soir meme : la simulation a 500 EUR virtuels (voir
--  ops/, run_demo.py) publiait ses positions dans CES DEUX TABLES,
--  les memes que lit l'application reelle (Allure et Alluxbot) --
--  l'operateur a vu une position "fermee a 600% de benefice" qui
--  n'existait pas. Le fix immediat a ete de COUPER la publication de
--  la demo (SUPABASE_URL/KEY vides pour ce processus).
--
--  Ce correctif-ci REOUVRE la publication, mais chaque ligne deposee
--  par la demo porte desormais `is_demo = true` -- l'application
--  reelle continue de ne montrer QUE `is_demo = false` (voir
--  robot.ts), et un nouvel onglet "Demo" affiche l'autre moitie,
--  clairement separee, jamais melangee.
-- ============================================================

alter table public.signals
  add column if not exists is_demo boolean not null default false;

comment on column public.signals.is_demo is
  'true = position de la simulation a capital virtuel (run_demo.py), '
  'jamais une vraie position du robot. Les ecrans "en direct" de '
  'l''application filtrent is_demo = false ; un ecran distinct montre '
  'is_demo = true.';

create index if not exists signals_demo_idx
  on public.signals (is_demo, status, published_at desc)
  where published_at is not null;

alter table public.alluxe_bot_alertes
  add column if not exists is_demo boolean not null default false;

comment on column public.alluxe_bot_alertes.is_demo is
  'true = alerte de la simulation a capital virtuel, jamais une vraie '
  'alerte du robot.';
