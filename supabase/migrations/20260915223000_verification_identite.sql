-- ============================================================
--  Verification d'identite pour Alluxe Bot -- PAS un mot de passe de
--  connexion (le compte de service gere deja l'authentification, voir
--  App.tsx). C'est un second gardien local : si jamais quelqu'un
--  d'autre que l'operateur ouvrait l'application, cette question filtre.
--
--  LA VRAIE REPONSE NE VIT NULLE PART DANS CE DEPOT, QUI EST PUBLIC.
--  Cette migration cree seulement la fonction et la table -- la valeur
--  elle-meme est inseree a part, par une commande jamais committee (voir
--  la conversation operateur du 15 sept.). Le depot ne contient donc
--  aucune trace du secret, ni dans le code client, ni dans l'historique
--  git.
-- ============================================================

create table public.secret_verification (
  id     text primary key,
  valeur text not null
);

alter table public.secret_verification enable row level security;
alter table public.secret_verification force row level security;
-- Aucune politique de lecture : meme un compte admin ne peut pas lire
-- cette table directement. Seule la fonction ci-dessous, en
-- SECURITY DEFINER, y accede.
revoke all on public.secret_verification from anon, authenticated;

create or replace function public.verifier_identite(reponse text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  attendu text;
begin
  select valeur into attendu from public.secret_verification where id = 'alluxe_bot';
  if attendu is null then
    return false;
  end if;
  return reponse = attendu;
end;
$$;

comment on function public.verifier_identite is
  'Compare la reponse a un secret stocke hors du code source. Rend '
  'seulement vrai/faux -- la valeur elle-meme n''est jamais exposee.';

revoke all on function public.verifier_identite(text) from public;
grant execute on function public.verifier_identite(text) to authenticated;
