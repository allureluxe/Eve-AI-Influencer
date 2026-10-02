-- Virements (depots +, retraits -) du compte reel depuis le debut de la
-- periode affichee. L'application s'en sert pour que la courbe du capital
-- ne montre pas les retraits comme des pertes (demande du 2 oct. 2026).
alter table public.alluxe_bot_comptes
  add column if not exists virements jsonb not null default '[]'::jsonb;
