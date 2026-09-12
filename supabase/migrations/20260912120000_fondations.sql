-- =====================================================================
--  FONDATIONS : types partages et utilitaires
-- =====================================================================
--
--  Application mobile de signaux crypto. Le robot Turtle qui tourne sur
--  le VPS ecrit ici via la cle `service_role` ; l'application lit avec la
--  cle `anon` au nom d'un utilisateur connecte.
--
--  DEUX PRINCIPES TIENNENT TOUT LE SCHEMA :
--
--  1. AUCUNE TABLE SANS RLS. Une table sans politique est lisible par
--     n'importe quel porteur de la cle `anon` — et cette cle est dans
--     l'application, donc publique. On l'active partout, meme sur les
--     tables « publiques ».
--
--  2. L'ECRITURE N'EST JAMAIS OUVERTE. `service_role` contourne RLS par
--     construction : il suffit donc de NE PAS ecrire de politique
--     d'ecriture pour que seul le robot puisse ecrire. On ne cree pas de
--     politique « pour la forme » qui donnerait l'illusion du contraire.
--
--  Les types sont des ENUM et non du texte libre : une faute de frappe
--  dans un `status` passerait inapercue et fausserait tous les comptages.
--  Ajouter une valeur reste possible (`ALTER TYPE ... ADD VALUE`).

create extension if not exists "pgcrypto";      -- gen_random_uuid()

-- --------------------------------------------------------------- types
create type signal_side   as enum ('buy', 'sell');
create type signal_status as enum ('active', 'closed_tp', 'closed_sl', 'cancelled');
create type event_impact  as enum ('low', 'medium', 'high');
create type user_tier     as enum ('free', 'plus');
create type risk_level    as enum ('prudent', 'normal', 'agressif');

-- ----------------------------------------------------------- utilitaire
--  `updated_at` tenu par la base et non par l'application : une mise a
--  jour faite depuis le SQL editor ou un script d'urgence doit laisser la
--  meme trace qu'une mise a jour faite par le robot.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
