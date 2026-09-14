-- =====================================================================
--  RESEAU SOCIAL -- vue agregee pour le fil
-- =====================================================================
--
--  L'application ne doit jamais calculer un compteur de likes en
--  rapatriant toutes les lignes de `post_likes` pour les compter cote
--  client -- ni ouvrir une deuxieme requete par post affiche. La base
--  agrege une fois, l'application affiche.

create view public.posts_public
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
join public.profiles pr on pr.id = p.auteur;

comment on view public.posts_public is
  'Le fil, compteurs deja calcules. `security_invoker = true` est '
  'ESSENTIEL : sans lui la vue s''executerait avec les droits de son '
  'proprietaire (postgres) et rendrait TOUS les posts a tout le monde, '
  'RLS de `posts` ou pas -- c''est le piege classique des vues sur '
  'Postgres < 15 / mal configurees.';

grant select on public.posts_public to authenticated;
