-- ============================================================
--  Version web d'Alluxe Bot (3 oct. 2026, decision de l'operateur) :
--  journal des essais de connexion.
--
--  L'APK s'authentifie avec le mot de passe du compte de service,
--  embarque dans le binaire. Une page web publique ne peut pas faire
--  pareil : son code se lit dans n'importe quel navigateur. La fonction
--  Edge `connexion-web` ouvre donc la session cote serveur, et seulement
--  apres une bonne reponse a l'ecran « annee » (meme secret que
--  `verifier_identite`).
--
--  L'adresse de la page est publique : ce journal plafonne les echecs.
--  Un compteur en memoire ne suffirait pas, chaque instance Edge a le sien.
-- ============================================================

create table public.connexion_web_essais (
  id     bigserial primary key,
  a      timestamptz not null default now(),
  reussi boolean not null
);

create index connexion_web_essais_a on public.connexion_web_essais (a desc);

alter table public.connexion_web_essais enable row level security;
alter table public.connexion_web_essais force row level security;
-- Aucune politique : seule la fonction Edge (cle de service) y touche.
revoke all on public.connexion_web_essais from anon, authenticated;
