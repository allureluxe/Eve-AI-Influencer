-- ============================================================
--  Etat public du robot : capital reel et variation du jour.
--
--  Demande par l'operateur pour l'ecran d'accueil de l'application,
--  AVANT connexion -- un visiteur qui n'a pas encore de compte doit
--  pouvoir voir ces deux chiffres. Contrairement a `signals`, ce n'est
--  pas une donnee a proteger : c'est exactement ce qu'on montre pour
--  donner envie de s'inscrire.
--
--  Une seule ligne (id fixe 'robot'). Pas d'historique ici -- la
--  courbe complete existe deja via `performance`, reservee aux
--  comptes connectes.
-- ============================================================

create table public.etat_public (
  id                 text primary key,
  capital_eur        numeric(12,2) not null,
  variation_jour_pct numeric(6,3)  not null,
  updated_at         timestamptz   not null default now()
);

comment on table public.etat_public is
  'Capital reel et variation du jour, lecture publique (sans compte). '
  'Ecrit uniquement par le robot (service_role) via ops/publier_etat_public.py.';

alter table public.etat_public enable row level security;

create policy "etat public : tout le monde lit"
  on public.etat_public for select
  to anon, authenticated
  using (true);

-- Aucune policy d'ecriture : seul service_role (qui contourne la RLS)
-- peut modifier cette table.
