-- ============================================================
--  Connexion par pseudo + mot de passe (decision de l'operateur,
--  13 septembre au soir) -- remplace le lien magique par e-mail.
--
--  Supabase Auth n'a pas de notion de "pseudo" : il identifie un
--  compte par e-mail (ou telephone). L'e-mail reste donc necessaire
--  a l'inscription (recuperation de compte, communications), mais
--  la CONNEXION se fait par pseudo : il faut pouvoir retrouver
--  l'e-mail a partir du pseudo, cote serveur, sans exposer toute la
--  table des profils a n'importe qui.
-- ============================================================

alter table public.profiles add column pseudo text;
alter table public.profiles add column email text;

alter table public.profiles add constraint pseudo_format
  check (pseudo is null or length(btrim(pseudo)) between 3 and 20);

-- Insensible a la casse : "Bob" et "bob" sont le meme pseudo, sinon
-- deux comptes pourraient se le disputer et personne ne s'y retrouve.
create unique index profiles_pseudo_idx
  on public.profiles (lower(pseudo))
  where pseudo is not null;

-- Le pseudo et l'e-mail arrivent dans les metadonnees passees a
-- `signUp` (`options.data.pseudo`) ; le declencheur existant les
-- recopie dans le profil au meme moment qu'il le cree, comme le
-- reste des champs par defaut.
create or replace function public.creer_profil_au_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, pseudo, email)
  values (new.id, new.raw_user_meta_data ->> 'pseudo', new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

-- ------------------------------------------------------- resolution
--
--  L'application ne lit jamais `profiles.email` directement (RLS : un
--  utilisateur ne voit que sa propre ligne). Cette fonction est le
--  SEUL acces public a cette colonne, et elle ne rend qu'un e-mail --
--  jamais une liste, jamais les autres champs du profil.
--
--  `security definer` : elle doit lire une ligne qui n'est pas celle
--  de l'appelant (il n'est pas encore connecte). C'est le meme
--  principe que `remise_pct` pour le parrainage Bitvavo.
create or replace function public.email_pour_pseudo(p_pseudo text)
returns text
language sql
security definer
set search_path = public
stable
as $$
  select email from public.profiles
  where lower(pseudo) = lower(btrim(p_pseudo))
  limit 1;
$$;

revoke all on function public.email_pour_pseudo(text) from public;
grant execute on function public.email_pour_pseudo(text) to anon, authenticated;

comment on function public.email_pour_pseudo(text) is
  'Seul acces public a profiles.email : resout un pseudo pour la '
  'connexion, ne rend jamais rien d''autre.';
