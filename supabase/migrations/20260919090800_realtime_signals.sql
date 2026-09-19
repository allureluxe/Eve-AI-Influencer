-- ============================================================
--  Active Supabase Realtime sur `signals` -- 19 sept.
--
--  L'ecran "en direct" de l'app (reel et demo) s'abonne aux
--  changements de cette table au lieu de la relire toutes les
--  10 secondes (demande explicite de l'operateur : « que ce soit
--  du direct »). Sans cette ligne, aucun evenement Realtime n'est
--  jamais emis -- verifie le 19 sept., `supabase_realtime` ne
--  portait encore aucune table.
-- ============================================================

alter publication supabase_realtime add table public.signals;
