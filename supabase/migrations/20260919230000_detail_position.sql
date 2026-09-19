-- ============================================================
--  De quoi ouvrir une position et la lire en detail -- 19 sept.
--
--  Demande de l'operateur : « quand je clique sur la position
--  ouverte je veux une page avec les infos -- a quel niveau ouvert,
--  a quelle heure, la quantite de lot, le stop loss d'ouverture ET
--  l'actuel s'il a monte ».
--
--  Deux de ces informations n'existaient nulle part dans la base.
--
--  1. LA QUANTITE. Le robot ne publiait que `position_size_pct`, le
--     pourcentage de capital RISQUE. L'application en deduisait la
--     mise en euros par la distance au stop -- un calcul juste, mais
--     qui ne rend pas le nombre d'unites achetees. On publie donc le
--     volume reel.
--
--  2. LE STOP COURANT. `stop_loss` est ecrit une seule fois, a
--     l'ouverture, et n'est jamais mis a jour : le stop suiveur
--     remonte cote robot sans que l'application le sache. Elle
--     affichait donc le stop d'ORIGINE en croyant montrer la
--     protection actuelle -- c'est-a-dire le contraire de ce qui
--     protege vraiment la position.
--
--     `stop_loss` garde son sens (le stop d'ouverture, qui ne doit
--     jamais changer, sinon tout l'historique des R devient faux) et
--     `stop_loss_actuel` porte le suiveur. Nul tant que le stop n'a
--     pas bouge : l'application retombe alors sur `stop_loss`.
-- ============================================================

alter table public.signals
  add column if not exists volume numeric,
  add column if not exists stop_loss_actuel numeric;

comment on column public.signals.volume is
  'Quantite reellement achetee, en unites de la crypto (pas en euros). '
  'Nul sur les lignes publiees avant le 19 sept. 2026.';

comment on column public.signals.stop_loss_actuel is
  'Stop suiveur courant. `stop_loss` reste le stop D''OUVERTURE et ne '
  'bouge jamais. Nul tant que le suiveur n''a pas deplace le stop.';
