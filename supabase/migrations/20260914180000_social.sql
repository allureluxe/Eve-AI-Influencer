-- =====================================================================
--  RESEAU SOCIAL -- PHASE 1 : posts, commentaires, likes, messages prives
-- =====================================================================
--
--  Demande de l'operateur (13 et 14 sept.) : les utilisateurs peuvent
--  poster leurs resultats, des images, des commentaires, et s'envoyer
--  des messages. C'est un second projet a part entiere -- voir la note
--  de memoire operateur sur l'ampleur reelle (profils enrichis, agent de
--  support, connexion du compte Bitvavo de chaque utilisateur). CE
--  FICHIER NE COUVRE QUE LES PRIMITIVES DE BASE : posts/commentaires/
--  likes/messages. Le reste reste a scoper.
--
--  DECISION DE SECURITE PRISE ICI, A CONFIRMER AVEC L'OPERATEUR :
--  `posts.resultat_pct` est un CHIFFRE DECLARE PAR L'UTILISATEUR, jamais
--  lu depuis un compte Bitvavo reel. Brancher le vrai compte de chaque
--  utilisateur demanderait de stocker des cles d'echange appartenant a
--  des inconnus -- une surface de risque sans rapport avec ce que ce
--  depot a fait jusqu'ici (le robot n'engage QUE l'argent de
--  l'operateur). Cette question reste ouverte, volontairement non
--  tranchee par ce fichier.
--
--  Meme discipline que le reste du depot : RLS active ET forcee sur
--  chaque table, `anon` ne recoit rien, `service_role` (le robot, le
--  VPS) n'est jamais utilise par l'application.

-- ---------------------------------------------------------------------
--  PROFIL : photo et presentation, facultatifs
-- ---------------------------------------------------------------------

alter table public.profiles
  add column photo_url text,
  add column bio        text check (char_length(bio) <= 280);

comment on column public.profiles.photo_url is
  'URL publique dans le bucket de stockage "avatars". Nulle tant que '
  'l''utilisateur n''en a pas depose une.';
comment on column public.profiles.bio is
  'Presentation courte, facultative. 280 caracteres : assez pour se '
  'presenter, trop court pour un roman -- meme logique que Signaux.tsx, '
  'on ne submerge pas un debutant.';


-- =====================================================================
--  POSTS
-- =====================================================================

create table public.posts (
  id            uuid primary key default gen_random_uuid(),
  auteur        uuid not null references auth.users (id) on delete cascade,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  texte         text check (char_length(texte) <= 1000),
  image_url     text,

  -- CHIFFRE DECLARE, PAS VERIFIE. Voir la note de securite en tete de
  -- fichier. L'application doit l'afficher avec un mot qui le dit
  -- ("declare par l'utilisateur"), jamais comme un fait etabli par le
  -- robot -- ce serait le confondre avec les signaux de la table
  -- `signals`, qui eux sont garantis exacts.
  resultat_pct  numeric,

  -- Un post sans texte ET sans image n'a rien a montrer.
  constraint posts_a_du_contenu check (texte is not null or image_url is not null)
);

comment on table public.posts is
  'Un post utilisateur : texte et/ou image, resultat facultatif '
  'DECLARE (non verifie). Distinct de `signals`, qui vient du robot.';

create trigger posts_touch
  before update on public.posts
  for each row execute function public.touch_updated_at();

create index posts_recents_idx on public.posts (created_at desc);
create index posts_auteur_idx  on public.posts (auteur);


-- =====================================================================
--  POST_LIKES
-- =====================================================================

create table public.post_likes (
  post_id    uuid not null references public.posts (id) on delete cascade,
  user_id    uuid not null references auth.users (id)   on delete cascade,
  created_at timestamptz not null default now(),

  -- Un like par personne et par post -- un double appui ne doit pas
  -- compter deux fois (meme raisonnement que signal_taken).
  primary key (post_id, user_id)
);

comment on table public.post_likes is 'Un « like » par personne et par post.';

create index post_likes_par_post_idx on public.post_likes (post_id);


-- =====================================================================
--  POST_COMMENTS
-- =====================================================================

create table public.post_comments (
  id         uuid primary key default gen_random_uuid(),
  post_id    uuid not null references public.posts (id) on delete cascade,
  auteur     uuid not null references auth.users (id)   on delete cascade,
  created_at timestamptz not null default now(),
  texte      text not null check (char_length(texte) between 1 and 500)
);

comment on table public.post_comments is 'Commentaires sur un post, par ordre chronologique.';

create index post_comments_par_post_idx on public.post_comments (post_id, created_at);


-- =====================================================================
--  MESSAGES PRIVES
-- =====================================================================

create table public.messages (
  id           uuid primary key default gen_random_uuid(),
  expediteur   uuid not null references auth.users (id) on delete cascade,
  destinataire uuid not null references auth.users (id) on delete cascade,
  created_at   timestamptz not null default now(),
  texte        text not null check (char_length(texte) between 1 and 2000),
  lu_le        timestamptz,

  constraint messages_pas_a_soi_meme check (expediteur <> destinataire)
);

comment on table public.messages is
  'Messages prives entre deux comptes. Aucune notion de conversation de '
  'groupe pour l''instant -- garde simple, comme le reste de l''application.';

-- Une conversation se lit par PAIRE de personnes, dans un sens ou l'autre :
-- sans cet index compose, chaque ouverture de fil balaie toute la table.
create index messages_conversation_idx
  on public.messages (least(expediteur, destinataire), greatest(expediteur, destinataire), created_at);

-- « Combien de messages non lus » pour le badge de l'onglet.
create index messages_non_lus_idx
  on public.messages (destinataire)
  where lu_le is null;


-- =====================================================================
--  ROW LEVEL SECURITY
-- =====================================================================

alter table public.posts         enable row level security;
alter table public.post_likes    enable row level security;
alter table public.post_comments enable row level security;
alter table public.messages      enable row level security;

alter table public.posts         force row level security;
alter table public.post_likes    force row level security;
alter table public.post_comments force row level security;
alter table public.messages      force row level security;

-- ---------------------------------------------------------------------
--  POSTS : lecture publique (entre connectes), ecriture par l'auteur
-- ---------------------------------------------------------------------

create policy "posts : lecture connectee"
  on public.posts for select
  to authenticated
  using (true);

create policy "posts : creer les siens"
  on public.posts for insert
  to authenticated
  with check ((select auth.uid()) = auteur);

create policy "posts : modifier les siens"
  on public.posts for update
  to authenticated
  using ((select auth.uid()) = auteur)
  with check ((select auth.uid()) = auteur);

create policy "posts : supprimer les siens"
  on public.posts for delete
  to authenticated
  using ((select auth.uid()) = auteur);

-- ---------------------------------------------------------------------
--  LIKES : lecture publique, chacun ne pose/retire que le sien
-- ---------------------------------------------------------------------

create policy "likes : lecture connectee"
  on public.post_likes for select
  to authenticated
  using (true);

create policy "likes : poser le sien"
  on public.post_likes for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "likes : retirer le sien"
  on public.post_likes for delete
  to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------
--  COMMENTAIRES : lecture publique, chacun ecrit et efface les siens
-- ---------------------------------------------------------------------

create policy "commentaires : lecture connectee"
  on public.post_comments for select
  to authenticated
  using (true);

create policy "commentaires : ecrire les siens"
  on public.post_comments for insert
  to authenticated
  with check ((select auth.uid()) = auteur);

create policy "commentaires : supprimer les siens"
  on public.post_comments for delete
  to authenticated
  using ((select auth.uid()) = auteur);

-- ---------------------------------------------------------------------
--  MESSAGES : chacun ne voit que ses propres conversations
-- ---------------------------------------------------------------------

--  NI PUBLIC NI PARTAGE. Contrairement aux posts, un message prive n'est
--  visible que par ses deux parties -- la politique le fait directement,
--  pas de table intermediaire necessaire pour deux personnes.
create policy "messages : lire les siens"
  on public.messages for select
  to authenticated
  using ((select auth.uid()) in (expediteur, destinataire));

create policy "messages : envoyer en son nom"
  on public.messages for insert
  to authenticated
  with check ((select auth.uid()) = expediteur);

--  Seul le DESTINATAIRE marque un message comme lu -- l'expediteur ne
--  doit pas pouvoir falsifier l'accuse de lecture de son propre message.
create policy "messages : marquer les siens comme lus"
  on public.messages for update
  to authenticated
  using ((select auth.uid()) = destinataire)
  with check ((select auth.uid()) = destinataire);


-- ---------------------------------------------------------------------
--  DROITS DE TABLE
-- ---------------------------------------------------------------------

revoke all on public.posts, public.post_likes, public.post_comments, public.messages
  from anon, authenticated;

grant select, insert, update, delete on public.posts         to authenticated;
grant select, insert, delete         on public.post_likes    to authenticated;
grant select, insert, delete         on public.post_comments to authenticated;
grant select, insert, update         on public.messages      to authenticated;

--  `anon` ne recoit rien, meme lecture : un visiteur non connecte ne voit
--  aucun post, aucun message -- coherent avec `signals`/`market_notes`.
