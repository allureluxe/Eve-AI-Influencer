-- ============================================================
--  Le capital au moment de l'ouverture -- 19 sept.
--
--  `position_size_pct` est un POURCENTAGE du capital. L'application
--  en deduit la mise et le gain en euros... en multipliant par le
--  capital COURANT. Tant que le capital ne bouge pas, ca tombe juste.
--
--  Des qu'il bouge, tout l'historique devient faux : une position
--  ouverte a 500 EUR et relue avec un capital de 3 300 affiche une
--  mise 6,6 fois trop grosse. Le cas se presente deux fois cette
--  semaine -- la simulation a 3 300 EUR demandee le 19 sept., et le
--  depot reel prevu le 28.
--
--  On enregistre donc le capital tel qu'il etait A L'OUVERTURE. Une
--  ligne publiee ne changera plus jamais de sens, quoi qu'il arrive
--  au compte ensuite.
--
--  Colonne nullable : les lignes deja publiees n'en ont pas, et
--  l'application retombe alors sur le capital courant comme avant.
-- ============================================================

alter table public.signals
  add column if not exists capital_eur numeric;

comment on column public.signals.capital_eur is
  'Capital du compte au moment de l''ouverture, en euros. Sert a '
  'reconstituer la mise et le gain reels (position_size_pct en est un '
  'pourcentage) meme apres un depot ou un retrait. Nul sur les lignes '
  'publiees avant le 19 sept. 2026.';
