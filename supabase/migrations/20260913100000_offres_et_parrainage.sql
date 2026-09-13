-- ============================================================
--  L'echelle d'abonnements ALLURE, et le parrainage Bitvavo
-- ============================================================
--
--  L'ECHELLE EST DEFINIE EN BASE, PAS DANS L'APPLICATION.
--
--  Trois endroits ont besoin de savoir ce que donne chaque palier :
--  la fonction Edge qui filtre les signaux, l'ecran qui presente les
--  offres, et le webhook qui applique un achat. Si chacun porte sa
--  propre copie, une divergence est inevitable — et sa forme la plus
--  probable est la pire : quelqu'un paie l'offre superieure et le
--  filtre continue de le traiter comme l'inferieure.
--
--  Une table de reference. Le serveur la lit, l'application la lit,
--  personne ne recopie.

-- ------------------------------------------------- l'echelle
--
--  `free` et `plus` existent deja (migration de fondation) : on ne les
--  retire pas, on complete. Un enum PostgreSQL ne se reordonne pas, et
--  les valeurs deja posees sur des profils doivent rester valides.
alter type user_tier add value if not exists 'essentiel' after 'free';
alter type user_tier add value if not exists 'pro'       after 'plus';

commit;   -- un nouveau libelle d'enum n'est utilisable qu'apres commit

create table public.offres (
  tier            user_tier primary key,
  rang            smallint not null unique,   -- 0 = gratuit, croissant
  nom             text not null,
  accroche        text not null,

  -- CE QUE LE PALIER DONNE. Le filtre serveur lit ces colonnes ; il ne
  -- teste jamais le nom du palier. Ajouter une offre demain ne demande
  -- donc aucune modification de code.
  toutes_paires   boolean not null default false,
  retard_minutes  integer not null default 120 check (retard_minutes >= 0),
  positions_direct boolean not null default false,
  note_du_matin   boolean not null default false,
  historique_complet boolean not null default false,
  export_csv      boolean not null default false,

  -- L'identifiant du produit cote RevenueCat / Google Play.
  produit_id      text,
  --  Le prix affiche est celui de Google Play, jamais celui-ci : la
  --  devise et les taxes changent selon le pays. Cette colonne ne sert
  --  qu'a ordonner et a l'affichage de secours quand le magasin est
  --  injoignable.
  prix_indicatif_eur numeric(6,2)
);

comment on table public.offres is
  'Reference unique de l''echelle d''abonnements. Le filtre serveur lit '
  'les CAPACITES, jamais le nom du palier.';

insert into public.offres
  (tier, rang, nom, accroche, toutes_paires, retard_minutes,
   positions_direct, note_du_matin, historique_complet, export_csv,
   produit_id, prix_indicatif_eur)
values
  ('free', 0, 'Decouverte',
   'Trois cryptos, deux heures apres le robot.',
   false, 120, false, false, false, false, null, 0),

  ('essentiel', 1, 'Essentiel',
   'Toutes les cryptos suivies, au moment ou le robot agit.',
   true, 0, false, false, false, false,
   'allure_essentiel_mensuel', 9.99),

  ('plus', 2, 'Plus',
   'Les positions en direct et le point de marche du matin.',
   true, 0, true, true, true, false,
   'allure_plus_mensuel', 19.99),

  ('pro', 3, 'Pro',
   'Tout, plus l''historique exportable.',
   true, 0, true, true, true, true,
   'allure_pro_mensuel', 39.99);

-- Lisible par tout le monde : c'est une grille tarifaire.
alter table public.offres enable row level security;
create policy offres_lecture_publique
  on public.offres for select to authenticated, anon using (true);

-- ------------------------------------------------ le parrainage
--
--  QUAND QUELQU'UN OUVRE UN COMPTE BITVAVO PAR NOTRE LIEN, IL A 10 %
--  DE REMISE SUR SON ABONNEMENT.
--
--  Ce qu'on peut verifier, et ce qu'on ne peut pas : Bitvavo ne nous
--  previent pas nommement de chaque ouverture de compte. On enregistre
--  donc une DECLARATION de l'utilisateur (`demande_le`), qui reste sans
--  effet jusqu'a ce qu'elle soit confirmee (`confirme_le`) apres
--  rapprochement avec le tableau de bord d'affiliation.
--
--  Accorder la remise sur simple declaration serait la donner a tout le
--  monde ; la refuser faute de preuve automatique serait ne jamais
--  tenir la promesse. La confirmation manuelle est la seule voie
--  honnete tant que Bitvavo ne renvoie rien.

create table public.parrainages (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  demande_le  timestamptz not null default now(),
  confirme_le timestamptz,
  -- Le jeton place dans le lien sortant : c'est lui qu'on retrouve
  -- dans le tableau de bord d'affiliation pour rapprocher.
  jeton       text not null unique,
  note        text
);

comment on table public.parrainages is
  'Declarations d''ouverture de compte Bitvavo via notre lien. La '
  'remise ne s''applique qu''une fois `confirme_le` renseigne — voir '
  'la migration 20260913100000 pour pourquoi la verification est '
  'manuelle.';

alter table public.parrainages enable row level security;

create policy parrainage_lecture_propre
  on public.parrainages for select to authenticated
  using (user_id = auth.uid());

--  L'utilisateur peut DECLARER, jamais CONFIRMER. La politique
--  n'autorise que l'insertion, et le champ `confirme_le` est refuse
--  par le declencheur ci-dessous.
create policy parrainage_declaration
  on public.parrainages for insert to authenticated
  with check (user_id = auth.uid());

create or replace function public.parrainage_non_auto_confirme()
returns trigger language plpgsql as $$
begin
  if current_user in ('authenticated', 'anon') then
    new.confirme_le := null;    -- l'utilisateur ne se confirme pas
  end if;
  return new;
end;
$$;

create trigger parrainage_verrou
  before insert or update on public.parrainages
  for each row execute function public.parrainage_non_auto_confirme();

-- La remise effective, calculee et non stockee : un champ recopie se
-- desynchronise le jour ou une confirmation est retiree.
create or replace function public.remise_pct(qui uuid)
returns numeric language sql stable as $$
  select case
    when exists (select 1 from public.parrainages
                  where user_id = qui and confirme_le is not null)
    then 10.0 else 0.0 end;
$$;

comment on function public.remise_pct is
  '10 % pour un parrainage Bitvavo confirme. Calculee a la demande : '
  'un pourcentage recopie sur le profil se desynchroniserait.';
