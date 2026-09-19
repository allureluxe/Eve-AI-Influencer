-- ============================================================
--  Plusieurs comptes demo en parallele -- 20 sept.
--
--  Demande de l'operateur : « une fois la methode trouvee tu vas
--  creer un 2e compte demo sur l'appli avec 3 300 EUR de capital
--  demo ».
--
--  C'est la bonne facon de comparer deux methodes : les faire
--  tourner sur le MEME marche, aux MEMES heures. Les essayer l'une
--  apres l'autre melangerait l'effet du reglage et celui du marche
--  -- exactement la faute que ce depot a deja payee (« une mesure
--  qui bouge deux variables ne dit rien sur aucune des deux »).
--
--  `is_demo` est un BOOLEEN : il distingue le simule du reel, pas
--  deux simulations entre elles. On ajoute donc le NOM du compte.
--
--  Valeur par defaut 'demo' : toutes les lignes deja publiees
--  appartiennent au premier compte, et rien ne change pour elles.
--  Le robot reel, lui, publie `is_demo=false` et le nom ne le
--  concerne pas -- il reste a 'demo' sans que ce soit lu.
-- ============================================================

alter table public.signals
  add column if not exists compte text not null default 'demo';

alter table public.alluxe_bot_alertes
  add column if not exists compte text not null default 'demo';

-- L'application filtre TOUJOURS sur (is_demo, compte) ensemble : sans
-- l'index, chaque ouverture de l'onglet balaierait la table entiere.
create index if not exists signals_compte_demo
  on public.signals (is_demo, compte, status);

create index if not exists alertes_compte_demo
  on public.alluxe_bot_alertes (is_demo, compte, created_at desc);

comment on column public.signals.compte is
  'Nom du compte simule qui a publie cette ligne (demo, demo2...). '
  'Sans objet quand is_demo=false. Permet de faire tourner deux '
  'methodes en parallele sur le meme marche sans les melanger.';

comment on column public.alluxe_bot_alertes.compte is
  'Nom du compte simule qui a emis cette alerte. Voir signals.compte.';
