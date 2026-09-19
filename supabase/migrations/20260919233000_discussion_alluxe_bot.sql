-- ============================================================
--  La discussion avec le robot, DANS l'application -- 19 sept.
--
--  Decision de l'operateur : « je n'ai plus besoin des messages
--  Telegram, l'application m'envoie des notifs. Tout ce que le
--  robot Telegram fait, je veux que ce soit identique sur mon
--  application. L'onglet Discussion, je veux que ce soit ici que je
--  reçois les messages et là où je peux écrire, comme la demande
--  rapport allure. »
--
--  Les ALERTES avaient deja leur table (`alluxe_bot_alertes`, meme
--  seuil et meme garde-fou que Telegram). Ce qui manquait est
--  l'autre sens : pouvoir ECRIRE au robot. C'est ce que fait cette
--  table.
--
--  LE RAPPORT EST STOCKE DANS LA LIGNE, pas sur une adresse
--  publique. Telegram le livrait en fichier dans une conversation
--  privee, pour une raison ecrite noir sur blanc dans
--  `ecoute_telegram.py` : « on ne met pas les finances de quelqu'un
--  sur le web ouvert pour economiser un clic ». Un lien de stockage,
--  meme obscur, reste une adresse que quelqu'un peut trouver. Le
--  HTML voyage donc dans la ligne, protegee par les memes regles que
--  le reste du compte.
-- ============================================================

create table if not exists public.alluxe_bot_discussion (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  -- 'operateur' = ce qu'il ecrit ; 'robot' = ce que le robot repond.
  auteur      text not null check (auteur in ('operateur', 'robot')),
  texte       text not null default '',
  -- La page ALLURE complete, telle que Telegram l'envoyait en fichier.
  -- Nulle sur un simple echange de texte.
  rapport_html text,
  rapport_titre text,
  -- Faux tant que le robot n'a pas traite la demande. Sans ce drapeau,
  -- l'ecouteur rejouerait chaque commande a chaque passage.
  traite      boolean not null default false
);

create index if not exists alluxe_bot_discussion_a_traiter
  on public.alluxe_bot_discussion (created_at)
  where auteur = 'operateur' and traite = false;

create index if not exists alluxe_bot_discussion_recent
  on public.alluxe_bot_discussion (created_at desc);

alter table public.alluxe_bot_discussion enable row level security;

-- Application PRIVEE, un seul utilisateur : le compte de service.
-- Meme regle que `alluxe_bot_alertes` -- tout utilisateur authentifie
-- lit et ecrit. Ce n'est pas un relachement : personne d'autre que
-- l'operateur ne possede d'identifiants sur ce projet.
drop policy if exists "discussion lecture" on public.alluxe_bot_discussion;
create policy "discussion lecture" on public.alluxe_bot_discussion
  for select to authenticated using (true);

drop policy if exists "discussion ecriture" on public.alluxe_bot_discussion;
create policy "discussion ecriture" on public.alluxe_bot_discussion
  for insert to authenticated with check (auteur = 'operateur');

-- Le fil doit arriver SANS rafraichir : c'est une conversation.
alter publication supabase_realtime add table public.alluxe_bot_discussion;

comment on table public.alluxe_bot_discussion is
  'Conversation entre l''operateur et le robot, dans l''onglet '
  'Discussion d''Alluxe Bot. Remplace la conversation Telegram '
  '(decision du 19 sept. 2026).';
