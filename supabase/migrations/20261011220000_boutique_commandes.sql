-- Boutique de Noël (alluxe.fr/noel) : une ligne par commande, du paiement à
-- l'expédition. Écrite par la fonction boutique-commande (création), par
-- boutique-apercu (validation du client) et par l'automate du VPS
-- (boutique/automate.py) pour tout le reste. RLS sans politique : seule la clé
-- de service lit et écrit, jamais le public.
--
-- Cycle :  attente_paiement -> payee -> portrait_pret -> validee
--          -> envoyee_imprimeur -> expediee
--          portrait_pret -> a_retoucher -> portrait_pret   (3 retouches max)
--          * -> a_verifier (l'opérateur regarde) | annulee | erreur
create table if not exists public.boutique_commandes (
  id                uuid primary key default gen_random_uuid(),
  cree_le           timestamptz not null default now(),
  maj_le            timestamptz not null default now(),
  statut            text not null default 'attente_paiement',
  produit           text not null,
  style             text not null,
  sujet             text not null,
  prenom            text not null,
  email             text not null,
  montant_eur       numeric(8,2) not null,
  photo_path        text not null,            -- bucket privé « boutique »
  portrait_path     text,                     -- dernier portrait généré
  impression_path   text,                     -- fichier haute définition envoyé à l'imprimeur
  retouches         int not null default 0,
  note_retouche     text,
  jeton             text not null unique,     -- lien secret d'aperçu envoyé au client
  stripe_session_id text unique,
  livraison         jsonb,                    -- adresse lue chez Stripe après paiement
  gelato_order_id   text,
  suivi_url         text,
  journal           jsonb not null default '[]'::jsonb,
  erreur            text
);
create index if not exists boutique_commandes_statut on public.boutique_commandes (statut);
alter table public.boutique_commandes enable row level security;

insert into storage.buckets (id, name, public)
values ('boutique', 'boutique', false)
on conflict (id) do nothing;
