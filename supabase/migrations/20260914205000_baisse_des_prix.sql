-- =====================================================================
--  BAISSE DES PRIX -- retour reel de l'operateur, 14 sept.
-- =====================================================================
--
-- « Les abonnements sont trop chers » : Essentiel 9,99 -> 4,99,
-- Plus 19,99 -> 9,99, Pro 39,99 -> 14,99. Deja applique a la main sur
-- la base reelle au moment de la demande ; ce fichier le rejoue pour
-- qu'un environnement reconstruit depuis zero retrouve les memes prix.

update public.offres set prix_indicatif_eur = 4.99  where tier = 'essentiel';
update public.offres set prix_indicatif_eur = 9.99  where tier = 'plus';
update public.offres set prix_indicatif_eur = 14.99 where tier = 'pro';
