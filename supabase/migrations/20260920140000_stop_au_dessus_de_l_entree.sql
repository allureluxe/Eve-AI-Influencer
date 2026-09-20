-- ============================================================
--  Un stop AU-DESSUS du prix d'achat n'est pas une erreur -- 20 sept.
--
--  La contrainte `stop_du_bon_cote` exigeait, pour un achat, que le
--  stop soit SOUS le prix d'entree. C'est vrai a la toute premiere
--  ouverture, et faux des qu'une pyramide se forme.
--
--  Quand le robot ajoute un etage, il fusionne : le prix d'entree
--  devient la moyenne ponderee, et le stop remonte sous la DERNIERE
--  unite -- donc souvent AU-DESSUS de cette moyenne. C'est l'etat
--  « a l'abri » : la position ne peut plus rien couter. C'est
--  exactement ce que la strategie cherche a atteindre, et c'est la
--  condition meme pour ajouter un etage
--  (`pyramide_locked_r_min = 0.01`).
--
--  CE QUE CA A COUTE. Le 20 septembre, le 2e etage de POL a ete
--  REFUSE par cette contrainte (erreur 23514). La publication est
--  partie dans la file d'attente, ou elle est restee. L'application
--  annoncait donc +13,32 EUR sur ce trade la ou le robot avait
--  encaisse +23,89. Et comme le refus etait avale par la file, RIEN
--  ne l'a signale -- c'est l'operateur qui a vu que les comptes ne
--  tombaient pas juste.
--
--  La regle devient donc : le stop doit exister et etre positif. Sa
--  position par rapport a l'entree ne dit plus rien d'une erreur --
--  elle dit seulement si la position est encore a risque ou deja a
--  l'abri, et les deux sont legitimes.
-- ============================================================

alter table public.signals drop constraint if exists stop_du_bon_cote;

-- On garde ce qui reste vrai : un stop est un prix, donc positif.
-- (`signals_stop_loss_check` le garantit deja ; on ne le double pas.)

comment on column public.signals.stop_loss is
  'Stop a l''OUVERTURE de cette ligne. Peut se trouver AU-DESSUS du '
  'prix d''achat sur un etage de pyramide : apres fusion, le prix '
  'd''entree est une moyenne et le stop est remonte sous la derniere '
  'unite. La position est alors « a l''abri » et ne peut plus perdre. '
  'Voir stop_loss_actuel pour le stop suiveur courant.';
