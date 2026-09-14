-- =====================================================================
--  PROFILS PUBLICS -- corrige un fil qui n'aurait montre que ses propres posts
-- =====================================================================
--
--  BUG TROUVE EN ECRIVANT L'ECRAN DU FIL, AVANT QU'IL N'ATTEIGNE
--  PERSONNE. `posts_public` (migration precedente) joint `profiles`
--  pour recuperer le pseudo de l'auteur, avec `security_invoker = true`
--  -- donc executee avec les droits ET LES POLITIQUES RLS de la personne
--  qui regarde. Or `profiles` n'a qu'une politique de lecture : « chacun
--  lit la sienne » (`auth.uid() = id`). Consequence : le JOIN n'aurait
--  jamais vu le profil d'un AUTRE utilisateur, et chaque post d'un tiers
--  aurait disparu du fil -- pas flou, pas cache : absent, jointure vide.
--
--  Un fil qui ne montre a chacun que ses propres posts n'est pas un
--  reseau social.
--
--  LA CORRECTION N'OUVRE PAS `profiles` EN GRAND. Elle cree une vue
--  etroite, exposant SEULEMENT ce qu'un pseudonyme public doit montrer
--  (id, pseudo, photo). Ni l'e-mail, ni le telephone, ni l'age, ni
--  l'adresse, ni le sexe n'y figurent -- ces colonnes restent
--  verrouillees derriere « chacun lit la sienne ». C'est la meme idee
--  que `email_pour_pseudo()` : une porte etroite et deliberee, jamais
--  la table entiere.
--
--  PAS DE `security_invoker` ICI, ET C'EST VOULU : cette vue doit
--  justement CONTOURNER la restriction de `profiles` pour rendre les
--  pseudos visibles a tous -- en n'exposant que des colonnes deja
--  publiques par nature (le pseudo sert a se faire reconnaitre).
create view public.profils_publics as
select id, pseudo, photo_url
from public.profiles;

comment on view public.profils_publics is
  'Colonnes publiques d''un profil (pseudo, photo). Contourne '
  'volontairement la RLS de `profiles` -- n''y ajouter QUE des colonnes '
  'deja destinees a etre vues de tous.';

grant select on public.profils_publics to authenticated;

-- `posts_public` rejoint desormais cette vue etroite plutot que
-- `profiles` directement -- meme forme, seule la source du pseudo change.
create or replace view public.posts_public
with (security_invoker = true)
as
select
  p.id,
  p.auteur,
  p.created_at,
  p.updated_at,
  p.texte,
  p.image_url,
  p.resultat_pct,
  pr.pseudo        as auteur_pseudo,
  pr.photo_url     as auteur_photo_url,
  (select count(*) from public.post_likes l
    where l.post_id = p.id)                          as likes_count,
  (select count(*) from public.post_comments cm
    where cm.post_id = p.id)                          as comments_count,
  exists (
    select 1 from public.post_likes l2
    where l2.post_id = p.id and l2.user_id = (select auth.uid())
  )                                                    as jaime_par_moi
from public.posts p
join public.profils_publics pr on pr.id = p.auteur;
