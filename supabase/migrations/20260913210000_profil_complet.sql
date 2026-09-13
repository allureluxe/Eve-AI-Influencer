-- ============================================================
--  Champs de profil supplementaires (decision de l'operateur,
--  13 septembre, tard le soir) : nom, prenom, telephone, age,
--  adresse, sexe (facultatif, statistiques).
--
--  Comme pseudo/email, ils arrivent dans les metadonnees passees a
--  `signUp` et le declencheur existant les recopie a la creation
--  du profil.
-- ============================================================

alter table public.profiles add column nom text;
alter table public.profiles add column prenom text;
alter table public.profiles add column telephone text;
alter table public.profiles add column age smallint;
alter table public.profiles add column adresse text;
alter table public.profiles add column sexe text;

alter table public.profiles add constraint age_plausible
  check (age is null or age between 13 and 120);

alter table public.profiles add constraint sexe_valide
  check (sexe is null or sexe in ('homme', 'femme', 'non precise'));

create or replace function public.creer_profil_au_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, pseudo, email, nom, prenom, telephone,
                                age, adresse, sexe)
  values (
    new.id,
    new.raw_user_meta_data ->> 'pseudo',
    new.email,
    new.raw_user_meta_data ->> 'nom',
    new.raw_user_meta_data ->> 'prenom',
    new.raw_user_meta_data ->> 'telephone',
    nullif(new.raw_user_meta_data ->> 'age', '')::smallint,
    new.raw_user_meta_data ->> 'adresse',
    new.raw_user_meta_data ->> 'sexe'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;
