-- =====================================================================
--  ABONNEMENT ANNUEL -- 10 % de remise sur le tarif mensuel x 12
-- =====================================================================
--
-- Demande de l'operateur (14 sept.) : « tu mets mensuelle ou annuelle,
-- si c'est annuelle tu mets 10 % moins cher, et tu montres le prix
-- normal comme une promo ».
--
-- PAS UNE NOUVELLE COLONNE SUR `profiles.tier`. La periode de
-- facturation ne change RIEN a ce qu'un compte peut voir -- un Pro
-- annuel a exactement les memes droits qu'un Pro mensuel. Elle ne
-- concerne que le prix et le produit Google Play factures, donc elle
-- reste dans `offres`, jamais dans le controle d'acces.

alter table public.offres
  add column produit_id_annuel        text,
  add column prix_indicatif_annuel_eur numeric(6,2);

comment on column public.offres.prix_indicatif_annuel_eur is
  'Prix TOTAL de l''annee, deja remise de 10 % sur (prix_indicatif_eur '
  'x 12). NULL sur le palier gratuit. Indicatif seulement, comme '
  'prix_indicatif_eur -- le prix reel vient de Google Play.';

-- 10 % de remise sur le tarif annualise, arrondi au centime.
update public.offres set
  produit_id_annuel = 'allure_essentiel_annuel',
  prix_indicatif_annuel_eur = round(4.99 * 12 * 0.9, 2)
where tier = 'essentiel';

update public.offres set
  produit_id_annuel = 'allure_plus_annuel',
  prix_indicatif_annuel_eur = round(9.99 * 12 * 0.9, 2)
where tier = 'plus';

update public.offres set
  produit_id_annuel = 'allure_pro_annuel',
  prix_indicatif_annuel_eur = round(14.99 * 12 * 0.9, 2)
where tier = 'pro';
